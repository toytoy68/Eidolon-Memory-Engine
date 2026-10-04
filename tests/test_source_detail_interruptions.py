"""Claude review of b18dad0/9819d6b: interruptions, concurrency, unfinished operations.

Guard cases from review on the VM (POSIX: fork + os._exit); synthetic corpus only.
"""
import multiprocessing
import os

import pytest

pytestmark = pytest.mark.skipif(not hasattr(os, 'fork'), reason='POSIX fork/os._exit')

from core.backend.filesystem import FilesystemBackend
from core.information.writes import FilesystemInformationWrites
from core.operations.readiness import check_readiness
from core.sources.validation import accept_detail
from tests.test_source_ai import setup, review
from tests.test_source_detail_identity import seed_v1


def backend(root):
    return FilesystemBackend(root/'memory/persistent', root/'memory/history')


def details(root):
    return sorted(m.information_id for m in backend(root).list(limit=10**6))


def _crash_in_child(root, draft, detail, actor, point):
    """Real process death (os._exit) at a chosen write step."""
    import core.backend.filesystem as fs
    import core.events.filesystem as ev
    if point == 'before_information_file':
        fs.FilesystemBackend._atomic_write = lambda *a, **k: os._exit(9)
    elif point == 'before_event':
        ev.FilesystemEventRepository.save = lambda *a, **k: os._exit(9)
    accept_detail(root, draft, detail=detail, actor=actor)
    os._exit(0)


def crash(root, draft, detail, actor, point):
    ctx = multiprocessing.get_context('fork')
    p = ctx.Process(target=_crash_in_child, args=(root, draft, detail, actor, point))
    p.start(); p.join(60)
    assert p.exitcode == 9


@pytest.mark.parametrize('point', ['before_information_file', 'before_event'])
def test_v2_interrupted_then_retry_with_variant_and_other_actor(tmp_path, point):
    _, record, extraction = setup(tmp_path); draft = review(record, extraction)
    crash(tmp_path, draft, draft['detail'], 'human', point)
    assert not check_readiness(tmp_path)['ready']
    with pytest.raises(ValueError, match='readiness'):
        accept_detail(tmp_path, draft, detail=draft['detail']+' ', actor='other')
    # The Information file exists only if the crash happened after its write.
    assert len(details(tmp_path)) == (point == 'before_event')
    FilesystemInformationWrites(backend(tmp_path)).recover()
    result = accept_detail(tmp_path, dict(draft, model='m2'), detail=draft['detail']+'  ', actor='other')
    assert result['information_id'].startswith('source-detail-v2-')
    assert details(tmp_path) == [result['information_id']]
    assert check_readiness(tmp_path)['ready']


def _seed_pending_v1(root, draft, point):
    """Old producer crashed: v1 operation journaled but not committed."""
    import core.backend.filesystem as fs
    import core.events.filesystem as ev
    if point == 'before_information_file':
        fs.FilesystemBackend._atomic_write = lambda *a, **k: os._exit(9)
    else:
        ev.FilesystemEventRepository.save = lambda *a, **k: os._exit(9)
    seed_v1(root, draft)
    os._exit(0)


@pytest.mark.parametrize('point', ['before_information_file', 'before_event'])
def test_pending_v1_then_new_analysis_after_recovery_does_not_duplicate(tmp_path, point):
    """Upgrade with an unfinished v1 acceptance: explicit recovery, then v2 analysis."""
    _, record, extraction = setup(tmp_path); draft = review(record, extraction)
    ctx = multiprocessing.get_context('fork')
    p = ctx.Process(target=_seed_pending_v1, args=(tmp_path, draft, point)); p.start(); p.join(60)
    assert p.exitcode == 9
    FilesystemInformationWrites(backend(tmp_path)).recover()
    result = accept_detail(tmp_path, dict(draft, model='m2'), detail=draft['detail']+' ', actor='other')
    assert details(tmp_path) == [result['information_id']]
    assert not result['information_id'].startswith('source-detail-v2-')


@pytest.mark.parametrize('point', ['before_information_file', 'before_event'])
def test_pending_v1_without_recovery_blocks_instead_of_duplicating(tmp_path, point):
    """A journaled v1 without recovery blocks new acceptances; no v2 twin appears."""
    _, record, extraction = setup(tmp_path); draft = review(record, extraction)
    ctx = multiprocessing.get_context('fork')
    p = ctx.Process(target=_seed_pending_v1, args=(tmp_path, draft, point)); p.start(); p.join(60)
    assert p.exitcode == 9
    # Readiness is what closes the duplicate path: the v2 scan only sees
    # published v1 files, not a journaled v1 operation without its file.
    assert not check_readiness(tmp_path)['ready']
    with pytest.raises(ValueError, match='readiness'):
        accept_detail(tmp_path, dict(draft, model='m2'), detail=draft['detail']+' ', actor='other')
    FilesystemInformationWrites(backend(tmp_path)).recover()
    assert len(details(tmp_path)) == 1, details(tmp_path)
    assert not details(tmp_path)[0].startswith('source-detail-v2-')


def _accept_worker(root, draft, index, barrier, queue):
    barrier.wait()
    detail = draft['detail'] + (' ' * (index % 3))
    queue.put(accept_detail(root, dict(draft, model=f'm{index}'), detail=detail, actor=f'a{index}'))


def test_processes_accept_variants_concurrently_publish_one_information(tmp_path):
    _, record, extraction = setup(tmp_path); draft = review(record, extraction)
    ctx = multiprocessing.get_context('fork')
    n = 6
    barrier = ctx.Barrier(n); queue = ctx.Queue()
    procs = [ctx.Process(target=_accept_worker, args=(tmp_path, draft, i, barrier, queue)) for i in range(n)]
    for p in procs: p.start()
    results = [queue.get(timeout=60) for _ in range(n)]
    for p in procs: p.join(60)
    assert all(p.exitcode == 0 for p in procs)
    assert len({r['information_id'] for r in results}) == 1
    assert len(details(tmp_path)) == 1


def test_processes_accept_while_v1_seed_published_concurrently(tmp_path):
    """v1 history present: concurrent new analyses resolve to the v1 Information."""
    _, record, extraction = setup(tmp_path); draft = review(record, extraction)
    first, _, _ = seed_v1(tmp_path, draft)
    ctx = multiprocessing.get_context('fork')
    n = 4
    barrier = ctx.Barrier(n); queue = ctx.Queue()
    procs = [ctx.Process(target=_accept_worker, args=(tmp_path, draft, i + 1, barrier, queue)) for i in range(n)]
    for p in procs: p.start()
    results = [queue.get(timeout=60) for _ in range(n)]
    for p in procs: p.join(60)
    assert all(r == first for r in results)
    assert details(tmp_path) == [first['information_id']]


def test_revised_v1_detail_is_matched_by_current_text_only(tmp_path):
    """Characterizes a limit: a revised v1 detail (revision 2) is matched by its
    current text and the creation result (revision 1) is returned; the original
    text no longer matches and yields a v2 Information with the same meaning."""
    from dataclasses import replace
    _, record, extraction = setup(tmp_path); draft = review(record, extraction)
    first, writer, key = seed_v1(tmp_path, draft)
    current = writer.backend.get(first['information_id'])
    revised = 'Lina vit à Lyon depuis 2020.'
    writer.update(replace(current, content=revised), previous_revision=1,
                  operation_id='edit-1', event_id='edit-event-1', actor='human', timestamp='2026-10-04T00:00:00Z')
    edited = accept_detail(tmp_path, dict(draft, model='m3'), detail=revised+' ', actor='other')
    assert edited == first and edited['revision'] == 1
    assert writer.backend.get(first['information_id']).revision == 2
    original = accept_detail(tmp_path, dict(draft, model='m2'), detail=draft['detail']+' ', actor='other')
    assert original['information_id'].startswith('source-detail-v2-')
    assert details(tmp_path) == sorted([first['information_id'], original['information_id']])
