# ==========================================================
# Projet      : Eidolon Memory Engine
# Organisation: Eidolon Core Technologies (ECT)
# Fichier     : tests/test_worker_journal.py
# Description : Journal recovery through real Markdown and isolated Qdrant.
# Standard    : Eidolon Presentation Standard v1
# ==========================================================
import pytest

from core.backend.filesystem import FilesystemBackend
from core.backend.models import Memory
from core.indexing.change_journal import ChangeJournal
from core.indexing.qdrant_index import QdrantIndex
from core.indexing.worker_canonical import CanonicalReader

qdrant = pytest.importorskip("qdrant_client")


@pytest.fixture
def world(tmp_path):
    class World:
        def __init__(self):
            self.root = tmp_path / "persistent"
            self.backend = FilesystemBackend(self.root, tmp_path / "history")
            self.journal = ChangeJournal(tmp_path / "changes.sqlite3")
            self.client = qdrant.QdrantClient(":memory:")
            self.index = QdrantIndex(self.client, "eidolon_journal_test",
                                     embed=lambda _: [1., 0.], dimensions=2,
                                     embedding_id="synthetic-v1", create=True)
            self.allowed = True
            self.writes = 0
            original = self.index.upsert_verified
            def upsert(*args, **kwargs):
                self.writes += 1
                return original(*args, **kwargs)
            self.index.upsert_verified = upsert

        def write(self, ident="doc", revision=1, published=True):
            memory = Memory(ident, content="synthetic source", revision=revision)
            if revision == 1:
                self.backend.store(memory)
            else:
                self.backend.update(ident, memory, previous_revision=revision - 1)
            _, digest = CanonicalReader(self.root)(ident)
            seq = self.journal.begin(ident, revision, "UPSERT", digest)
            if published:
                self.journal.published(seq)
            return seq

        def worker(self, **kwargs):
            from core.indexing.worker_journal import JournalUpsertWorker
            return JournalUpsertWorker(
                self.journal, canonical_root=self.root, index=self.index,
                authorize=lambda *args: self.allowed, profile_id="owner",
                expected_profile_id="owner", expected_model_id="synthetic-v1", **kwargs)

        def states(self):
            return {i.sequence: i.state for i in self.journal.pending(limit=1000)}

    w = World()
    yield w
    w.client.close()


def test_verified_upsert_advances_real_journal_and_replay_is_noop(world):
    seq = world.write()
    result = world.worker().run_once()
    assert result.status == "DONE"
    assert result.indexed == (seq,)
    assert world.states() == {}
    assert world.index.evidence_for("doc").revision == 1
    assert world.worker().run_once().indexed == ()
    assert world.writes == 1


def test_lost_ack_stays_pending_then_recovers_without_reembedding(world, monkeypatch):
    seq = world.write()
    original = world.index.upsert_verified
    def lose_ack(*args, **kwargs):
        original(*args, **kwargs)
        raise ConnectionError("ack lost")
    monkeypatch.setattr(world.index, "upsert_verified", lose_ack)
    assert world.worker().run_once().status == "INDEX_UNAVAILABLE"
    assert world.states() == {seq: "PUBLISHED"}
    monkeypatch.setattr(world.index, "upsert_verified", original)
    assert world.worker().run_once().indexed == (seq,)
    assert world.writes == 1


def test_interrupted_canonical_publication_recovers_in_two_rounds(world):
    seq = world.write(published=False)
    first = world.worker().run_once()
    assert first.published == (seq,) and first.indexed == ()
    assert world.states() == {seq: "PUBLISHED"} and world.writes == 0
    assert world.worker().run_once().indexed == (seq,)


@pytest.mark.parametrize("published", [True, False])
def test_unreadable_or_missing_canon_never_promotes_journal(world, published):
    seq = world.write(published=published)
    (world.root / "doc.md").unlink()
    result = world.worker().run_once()
    assert result.deferred == ((seq, "UNVERIFIED"),)
    assert world.states() == {seq: "PUBLISHED" if published else "INTENT"}
    assert world.writes == 0


@pytest.mark.parametrize("allowed", [False, 1, "yes", None])
def test_rights_must_be_exactly_true(world, allowed):
    seq = world.write()
    world.allowed = allowed
    assert world.worker().run_once().deferred == ((seq, "FORBIDDEN"),)
    assert world.states() == {seq: "PUBLISHED"} and world.writes == 0


def test_rights_revoked_during_upsert_keep_pending(world, monkeypatch):
    seq = world.write()
    original = world.index.upsert_verified
    def revoke(*args, **kwargs):
        result = original(*args, **kwargs)
        world.allowed = False
        return result
    monkeypatch.setattr(world.index, "upsert_verified", revoke)
    assert world.worker().run_once().indexed == ()
    assert world.states() == {seq: "PUBLISHED"}


def test_canon_changed_during_embedding_keeps_old_intent_pending(world, monkeypatch):
    first = world.write()
    original = world.index.upsert_verified
    def edit(*args, **kwargs):
        world.write(revision=2)
        return original(*args, **kwargs)
    monkeypatch.setattr(world.index, "upsert_verified", edit)
    assert world.worker().run_once().indexed == ()
    assert world.states()[first] == "PUBLISHED"
    monkeypatch.setattr(world.index, "upsert_verified", original)
    result = world.worker().run_once()
    assert result.deferred == ((first, "SUPERSEDED_REQUIRES_REVIEW"),)
    assert len(result.indexed) == 1
    assert world.index.evidence_for("doc").revision == 2


def test_same_revision_canonical_corruption_does_not_write(world):
    seq = world.write()
    p = world.root / "doc.md"
    p.write_text(p.read_text().replace("synthetic source", "changed source"))
    assert world.worker().run_once().deferred == ((seq, "CANONICAL_MISMATCH"),)
    assert world.states() == {seq: "PUBLISHED"} and world.writes == 0


def test_conflicting_point_same_revision_requires_review(world):
    seq = world.write()
    memory, _ = CanonicalReader(world.root)("doc")
    world.index.upsert_verified(memory, canonical_sha256="0" * 64)
    assert world.worker().run_once().deferred == ((seq, "INDEX_CONFLICT"),)
    assert world.states() == {seq: "PUBLISHED"} and world.writes == 1


def test_legacy_point_without_proof_is_rewritten_before_indexed(world):
    seq = world.write()
    memory, _ = CanonicalReader(world.root)("doc")
    world.index.upsert(memory)
    assert world.index.evidence_for("doc") is None
    assert world.worker().run_once().indexed == (seq,)
    assert world.writes == 1


def test_index_read_failure_has_no_journal_effect(world, monkeypatch):
    seq = world.write()
    def unavailable(*args):
        raise ConnectionError("offline")
    monkeypatch.setattr(world.index, "evidence_for", unavailable)
    assert world.worker().run_once().status == "INDEX_UNAVAILABLE"
    assert world.states() == {seq: "PUBLISHED"} and world.writes == 0


def test_model_mismatch_refuses_even_intent_publication(world):
    seq = world.write(published=False)
    world.index.embedding_id = "other-model"
    assert world.worker().run_once().status == "INDEX_INCOMPATIBLE"
    assert world.states() == {seq: "INTENT"} and world.writes == 0


def test_deletion_is_deferred_without_deleting_or_acknowledging(world):
    seq = world.journal.begin("doc", 1, "DELETE")
    world.journal.published(seq)
    assert world.worker().run_once().deferred == ((seq, "DELETE_REQUIRES_REVIEW"),)
    assert world.states() == {seq: "PUBLISHED"}


def test_truncation_and_backwards_clock_refuse_before_effect(world):
    a = world.write("a")
    b = world.write("b")
    assert world.worker().run_once(limit=1).status == "TRUNCATED"
    assert world.worker().run_once(now=1).status == "REFUSED"
    assert world.states() == {a: "PUBLISHED", b: "PUBLISHED"}
    assert world.writes == 0


def test_writer_lock_makes_other_worker_busy(world):
    import threading
    from core.persistence import exclusive_write
    world.write()
    worker = world.worker()
    results = []
    with exclusive_write(world.root):
        t = threading.Thread(target=lambda: results.append(worker.run_once()))
        t.start()
        t.join(5)
        assert not t.is_alive()
    assert results[0].status == "BUSY" and world.writes == 0


def test_writer_in_another_process_blocks_worker(world):
    import subprocess
    import sys
    world.write()
    child = subprocess.Popen(
        [sys.executable, "-c",
         "import sys; from core.persistence import exclusive_write; "
         "lock=exclusive_write(sys.argv[1]); lock.__enter__(); "
         "print('locked', flush=True); sys.stdin.read(1); lock.__exit__(None,None,None)",
         str(world.root)], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, text=True)
    try:
        # Readiness is signalled only after the OS lock is held.
        import selectors
        with selectors.DefaultSelector() as selector:
            selector.register(child.stdout, selectors.EVENT_READ)
            assert selector.select(timeout=10), "child did not acquire lock"
        assert child.stdout.readline().strip() == "locked"
        assert world.worker().run_once().status == "BUSY"
        assert world.writes == 0
        _, error = child.communicate("x", timeout=10)
        assert child.returncode == 0, error
    finally:
        if child.poll() is None:
            child.kill()
            child.communicate(timeout=5)


def test_two_workers_do_not_duplicate_the_effect(world):
    import threading
    world.write()
    workers = [world.worker(), world.worker()]
    reports, errors = [], []
    barrier = threading.Barrier(2)
    def run(worker):
        try:
            barrier.wait(timeout=5)
            reports.append(worker.run_once())
        except BaseException as exc:
            errors.append(exc)
    threads = [threading.Thread(target=run, args=(w,)) for w in workers]
    for t in threads:
        t.start()
    for t in threads:
        t.join(10)
        assert not t.is_alive()
    assert not errors
    assert {r.status for r in reports} <= {"DONE", "BUSY"}
    assert world.states() == {} and world.writes == 1


def test_journal_changed_during_indexing_is_not_marked_indexed(world, monkeypatch):
    seq = world.write()
    original = world.index.upsert_verified
    def change(*args, **kwargs):
        result = original(*args, **kwargs)
        world.journal.close_terminal(seq, "SUPERSEDED", "external review")
        return result
    monkeypatch.setattr(world.index, "upsert_verified", change)
    assert world.worker().run_once().deferred == ((seq, "JOURNAL_CHANGED"),)
    import sqlite3
    with sqlite3.connect(world.journal.path) as db:
        assert db.execute("SELECT state FROM intents WHERE seq=?", (seq,)).fetchone() == ("SUPERSEDED",)


def test_process_death_after_point_write_recovers_from_disk(tmp_path):
    import subprocess
    import sys
    import textwrap
    from core.indexing.worker_journal import JournalUpsertWorker
    root = tmp_path / "persistent"
    backend = FilesystemBackend(root, tmp_path / "history")
    backend.store(Memory("doc", content="process crash"))
    _, digest = CanonicalReader(root)("doc")
    journal = ChangeJournal(tmp_path / "changes.sqlite3")
    seq = journal.begin("doc", 1, "UPSERT", digest)
    journal.published(seq)
    child = textwrap.dedent('''
        import os, sys
        from pathlib import Path
        from qdrant_client import QdrantClient
        from core.indexing.change_journal import ChangeJournal
        from core.indexing.qdrant_index import QdrantIndex
        from core.indexing.worker_journal import JournalUpsertWorker
        base = Path(sys.argv[1])
        journal = ChangeJournal(base / "changes.sqlite3")
        def crash(expected, after):
            assert after == "INDEXED"
            os._exit(73)
        journal.advance_verified = crash
        client = QdrantClient(path=str(base / "qdrant"))
        index = QdrantIndex(client, "eidolon_crash_test", embed=lambda _: [1., 0.],
                            dimensions=2, embedding_id="synthetic-v1", create=True)
        JournalUpsertWorker(journal, canonical_root=base / "persistent", index=index,
                            authorize=lambda *args: True, profile_id="owner",
                            expected_profile_id="owner", expected_model_id="synthetic-v1").run_once()
    ''')
    result = subprocess.run([sys.executable, "-c", child, str(tmp_path)],
                            capture_output=True, text=True, timeout=30)
    assert result.returncode == 73, result.stderr
    assert journal.pending()[0].state == "PUBLISHED"
    client = qdrant.QdrantClient(path=str(tmp_path / "qdrant"))
    try:
        def no_reembedding(_):
            pytest.fail("recovery must use the persisted proof")
        index = QdrantIndex(client, "eidolon_crash_test", embed=no_reembedding,
                            dimensions=2, embedding_id="synthetic-v1")
        report = JournalUpsertWorker(journal, canonical_root=root, index=index,
                                    authorize=lambda *args: True, profile_id="owner",
                                    expected_profile_id="owner", expected_model_id="synthetic-v1").run_once()
        assert report.indexed == (seq,) and journal.pending() == ()
    finally:
        client.close()


def test_fsync_failure_during_intent_recovery_keeps_intent(world, monkeypatch):
    import os
    seq = world.write(published=False)
    def failed_sync(fd):
        raise OSError("disk failure")
    monkeypatch.setattr(os, "fsync", failed_sync)
    assert world.worker().run_once().published == ()
    assert world.states() == {seq: "INTENT"} and world.writes == 0


def test_journal_compare_and_advance_rejects_stale_complete_row(world):
    from dataclasses import replace
    seq = world.write()
    intent = world.journal.pending()[0]
    for stale in [replace(intent, revision=2), replace(intent, canonical_sha256="0" * 64),
                  replace(intent, information_id="other"), replace(intent, created=intent.created - 1)]:
        assert world.journal.advance_verified(stale, "INDEXED") is False
    assert world.states() == {seq: "PUBLISHED"}


def test_point_changed_during_final_readback_keeps_journal_pending(world, monkeypatch):
    from dataclasses import replace
    seq = world.write()
    memory, digest = CanonicalReader(world.root)("doc")
    world.index.upsert_verified(memory, canonical_sha256=digest)
    original = world.index.evidence_for
    calls = []
    def switch(ident):
        calls.append(ident)
        point = original(ident)
        return point if len(calls) == 1 else replace(point, generation="switched-generation")
    monkeypatch.setattr(world.index, "evidence_for", switch)
    assert world.worker().run_once().indexed == ()
    assert world.states() == {seq: "PUBLISHED"}
