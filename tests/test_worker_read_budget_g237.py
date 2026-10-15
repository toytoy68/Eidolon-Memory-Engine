# ==========================================================
# Projet      : Eidolon Memory Engine
# Organisation: Eidolon Core Technologies (ECT)
# Fichier     : tests/test_worker_read_budget_g237.py
# Description : Bounded real canonical reads on every journal transition.
# Standard    : Eidolon Presentation Standard v1
# ==========================================================
import os
import pytest
from core.backend.filesystem import FilesystemBackend
from core.backend.models import Memory
from core.indexing.worker_canonical import CanonicalReader
from tests.test_worker_journal import world


def document(world, ident, size, published=True):
    world.backend.store(Memory(ident, content='x' * size))
    _, digest = CanonicalReader(world.root)(ident)
    seq = world.journal.begin(ident, 1, 'UPSERT', digest)
    if published:
        world.journal.published(seq)
    return seq


@pytest.mark.parametrize('published', [True, False])
def test_default_bound_rejects_valid_oversized_document_before_embedding(world, published):
    seq = document(world, 'large', 8*1024*1024, published)
    result = world.worker().run_once()
    assert result.deferred == ((seq, 'CANONICAL_TOO_LARGE'),)
    assert world.writes == 0
    assert world.states() == {seq: 'PUBLISHED' if published else 'INTENT'}


@pytest.mark.parametrize('method', ['run_once', 'run_page'])
def test_oversized_row_does_not_starve_valid_tail(world, method):
    bad = document(world, 'large', 4096)
    good = world.write('small')
    result = getattr(world.worker(max_file_bytes=2048), method)()
    if method == 'run_page':
        assert result.exhausted
        result = result.result
    assert result.deferred == ((bad, 'CANONICAL_TOO_LARGE'),)
    assert result.indexed == (good,) and world.writes == 1
    assert world.states() == {bad: 'PUBLISHED'}


@pytest.mark.parametrize('published', [True, False])
def test_exact_file_bound_allows_both_publication_and_indexing(world, published):
    seq = world.write(published=published)
    worker = world.worker(max_file_bytes=(world.root/'doc.md').stat().st_size)
    if not published:
        assert worker.run_once().published == (seq,)
    assert worker.run_once().indexed == (seq,)
    assert world.writes == 1


@pytest.mark.parametrize('value', [None, True, 0, -1, 1.5, float('inf'), 2**64])
def test_invalid_or_unbounded_configuration_is_refused(world, value):
    with pytest.raises(ValueError):
        world.worker(max_file_bytes=value)


def test_lower_budget_keeps_existing_verified_point_pending_until_explicit_retry(world):
    seq = world.write()
    memory, digest = CanonicalReader(world.root)('doc')
    world.index.upsert_verified(memory, canonical_sha256=digest)
    size = (world.root/'doc.md').stat().st_size
    assert world.worker(max_file_bytes=size-1).run_once().deferred == ((seq, 'CANONICAL_TOO_LARGE'),)
    assert world.states() == {seq: 'PUBLISHED'} and world.writes == 1
    assert world.worker(max_file_bytes=size).run_once().indexed == (seq,)
    assert world.writes == 1  # adopt read-back, no duplicate embedding


def test_growing_file_is_still_read_with_a_hard_byte_bound(world, monkeypatch):
    seq = world.write()
    path = world.root/'doc.md'
    bound = path.stat().st_size
    original = os.fdopen
    sizes = []
    class Handle:
        def __init__(self, wrapped): self.wrapped = wrapped
        def __enter__(self): return self
        def __exit__(self, *args): return self.wrapped.__exit__(*args)
        def fileno(self): return self.wrapped.fileno()
        def read(self, size=-1):
            sizes.append(size)
            assert size == bound+1
            with path.open('ab') as stream: stream.write(b'x'*1024)
            return self.wrapped.read(size)
    def growing(fd, *args, **kwargs):
        handle = original(fd, *args, **kwargs)
        return Handle(handle) if args == ('rb',) else handle
    monkeypatch.setattr(os, 'fdopen', growing)
    result = world.worker(max_file_bytes=bound).run_once()
    assert result.deferred == ((seq, 'CANONICAL_TOO_LARGE'),)
    assert sizes == [bound+1] and world.writes == 0
    assert world.states() == {seq: 'PUBLISHED'}


def test_growth_after_index_effect_prevents_indexed_transition(world, monkeypatch):
    seq = world.write()
    path = world.root/'doc.md'
    bound = path.stat().st_size
    original = world.index.upsert_verified
    def grow(*args, **kwargs):
        point = original(*args, **kwargs)
        with path.open('ab') as stream: stream.write(b'x')
        return point
    monkeypatch.setattr(world.index, 'upsert_verified', grow)
    result = world.worker(max_file_bytes=bound).run_once()
    assert result.deferred == ((seq, 'CANONICAL_TOO_LARGE'),)
    assert world.writes == 1 and world.states() == {seq: 'PUBLISHED'}


def test_growth_before_durable_publication_keeps_intent(world):
    seq = world.write(published=False)
    path = world.root/'doc.md'
    bound = path.stat().st_size
    worker = world.worker(max_file_bytes=bound)
    calls = []
    def authorize(*args):
        calls.append(args)
        if len(calls) == 2:
            with path.open('ab') as stream: stream.write(b'x')
        return True
    worker.authorize = authorize
    assert worker.run_once().deferred == ((seq, 'CANONICAL_TOO_LARGE'),)
    assert world.states() == {seq: 'INTENT'} and world.writes == 0
