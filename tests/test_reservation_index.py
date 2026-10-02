"""Index deletion, stale bytes and interrupted publications cannot free owners."""
from collections import Counter
from dataclasses import replace
import json
import multiprocessing
import os
from pathlib import Path
import subprocess
import sys

import pytest

from core.backend.models import Memory
from core.information.reservation_index import ReservationIndex
from core.information.write_journal import InformationWriteJournal
from core.operations.errors import OperationConflict, OperationRepositoryError
from core.operations.readiness import check_readiness
from core.persistence import exclusive_write
from tests.test_information_batches import create, update, crash, competitor
from tests.test_journal_scan_cost import writer_at, command, join, create_pending_update
from tools.vm_acceptance import hashes


def index_for(writer):
    return ReservationIndex(writer.journal, writer)


def refresh(writer):
    with exclusive_write(writer.backend.persistent_root), exclusive_write(writer.operations.root):
        return index_for(writer).refresh()


@pytest.mark.parametrize('compact', [False, True])
def test_unchanged_history_skips_strict_decoding_but_next_writer_reads_changed_entry(tmp_path, monkeypatch, compact):
    writer = writer_at(tmp_path)
    for i in range(8):
        writer.create(Memory(str(i), content='sensitive text'), **command(str(i)))
        if compact:
            writer.compact('op-' + str(i))
    assert writer.rebuild_reservation_index()['validated'] == 8
    assert 'sensitive text' not in index_for(writer).path.read_text()
    writer = writer_at(tmp_path)  # fresh instance uses the persistent derived view
    reads = Counter()
    original = writer.journal.read
    def read(opid):
        reads[opid] += 1
        return original(opid)
    monkeypatch.setattr(writer.journal, 'read', read)
    writer.execute_batch([create('new'), update('new', 1, 'updated', 'edit')])
    assert all(reads['op-' + str(i)] == 0 for i in range(8))
    assert writer.backend.get('new').revision == 2
    assert index_for(writer).status()['status'] == 'STALE'
    view, report = refresh(writer)
    assert report == dict(status='CURRENT', entries=10, validated=2, reused=8)
    assert view == writer.journal.reservations()


@pytest.mark.parametrize('damage', ['deleted', 'truncated', 'unknown_version', 'removed_reservation'])
def test_disposable_index_reconstructs_from_sources_and_preserves_event_owner(tmp_path, damage):
    writer = writer_at(tmp_path)
    writer.create(Memory('old'), **command('old'))
    writer.compact('op-old')
    writer.rebuild_reservation_index()
    index = index_for(writer)
    expected = index.path.read_bytes()
    if damage == 'deleted':
        index.path.unlink()
    elif damage == 'truncated':
        index.path.write_text('{')
    else:
        data = json.loads(index.path.read_text())
        if damage == 'unknown_version':
            data['version'] = 999
        else:
            data['entries']['op-old']['event'] = 'freed'
        index.path.write_text(json.dumps(data))
    writer.events._path('event-old').unlink()
    restarted = writer_at(tmp_path)
    with pytest.raises(OperationConflict, match='reserved'):
        restarted.create(Memory('new'), **command('new', 'event-old'))
    assert restarted.backend.get('new') is None
    restarted.rebuild_reservation_index()
    assert index.path.read_bytes() == expected


@pytest.mark.parametrize('mutation', ['same_size_mtime', 'unknown_receipt', 'divergent_pair'])
def test_changed_journal_is_strictly_revalidated_before_any_new_effect(tmp_path, monkeypatch, mutation):
    writer = writer_at(tmp_path)
    writer.create(Memory('old'), **command('old'))
    if mutation == 'divergent_pair':
        import core.information.compaction as module
        with monkeypatch.context() as patch:
            patch.setattr(module, 'durable_unlink', lambda *a: (_ for _ in ()).throw(RuntimeError('stop')))
            with pytest.raises(RuntimeError):
                writer.compact('op-old')
    else:
        writer.compact('op-old')
    writer.rebuild_reservation_index()
    path = writer.journal.receipt_path('op-old')
    old_stat = path.stat()
    if mutation == 'same_size_mtime':
        original = path.read_text()
        path.write_text(original.replace('"format_version":1', '"format_version":9'))
        assert path.stat().st_size == old_stat.st_size and path.read_text() != original
        os.utime(path, ns=(old_stat.st_atime_ns, old_stat.st_mtime_ns))
    else:
        data = json.loads(path.read_text())
        data.update(format_version=999) if mutation == 'unknown_receipt' else data.update(event_sha256='f' * 64)
        path.write_text(json.dumps(data))
    assert index_for(writer).status()['status'] == 'STALE'
    before = hashes(tmp_path)
    with pytest.raises(OperationConflict):
        writer.create(Memory('new'), **command('new'))
    assert hashes(tmp_path) == before
    assert not check_readiness(tmp_path)['ready']


def test_inserted_pending_and_failed_entries_reserve_targets_then_refresh_after_resume(tmp_path, monkeypatch):
    from core.operations.models import OperationStatus
    writer = writer_at(tmp_path)
    writer.create(Memory('old'), **command('old'))
    writer.rebuild_reservation_index()
    with monkeypatch.context() as patch:
        patch.setattr(writer.events, 'save', lambda *a: (_ for _ in ()).throw(RuntimeError('stop')))
        with pytest.raises(RuntimeError):
            writer.update(replace(writer.backend.get('old'), content='pending'), previous_revision=1, **command('pending'))
    current = writer.backend.get('old')
    with pytest.raises(OperationConflict, match='pending'):
        writer.update(current, previous_revision=2, **command('other'))
    writer.resume('op-pending')
    assert writer.update(current, previous_revision=2, **command('other'))['revision'] == 3
    with monkeypatch.context() as patch:
        patch.setattr(writer.events, 'save', lambda *a: (_ for _ in ()).throw(RuntimeError('stop')))
        with pytest.raises(RuntimeError):
            writer.create(Memory('failed'), **command('failed'))
    op = writer.operations.get('op-failed')
    writer.operations.update(replace(op, status=OperationStatus.FAILED))
    with pytest.raises(OperationConflict, match='pending'):
        writer.update(writer.backend.get('failed'), previous_revision=1, **command('blocked'))


def test_compaction_removes_snapshot_from_index_and_terminal_replay_never_resurrects(tmp_path):
    writer = writer_at(tmp_path)
    commands = [create('old')]
    writer.execute_batch(commands)
    writer.rebuild_reservation_index()
    writer.compact('op-old')
    view, report = refresh(writer)
    assert report['validated'] == 1
    assert json.loads(index_for(writer).path.read_text())['entries']['op-old']['sources'][0] is None
    writer.backend.delete_request('old', 'human', 'remove', 1, 'delete')
    writer.backend.approve_delete('old', 'delete')
    assert writer.execute_batch(commands)['status'] == 'COMPLETED'
    assert writer.backend.get('old') is None and 'event-old' in view.event_ids


def test_canonical_entry_removal_does_not_leave_phantom_index_owner(tmp_path):
    writer = writer_at(tmp_path)
    writer.create(Memory('old'), **command('old'))
    writer.rebuild_reservation_index()
    writer.operations._path('op-old').unlink()  # external loss: index cannot replace canonical history
    assert index_for(writer).status()['status'] == 'STALE'
    view, report = refresh(writer)
    assert report['entries'] == 0 and view == writer.journal.reservations()


@pytest.mark.parametrize('location', ['index', 'derived', 'journal'])
def test_symlink_boundary_refused_without_touching_destination(tmp_path, location):
    writer = writer_at(tmp_path)
    writer.create(Memory('old'), **command('old'))
    writer.rebuild_reservation_index()
    index = index_for(writer)
    target = tmp_path / 'elsewhere'
    if location == 'derived':
        index.path.parent.rename(target)
        index.path.parent.symlink_to(target, target_is_directory=True)
    else:
        path = index.path if location == 'index' else writer.operations._path('op-old')
        path.rename(target); path.symlink_to(target)
    before = hashes(tmp_path)
    with pytest.raises((OperationRepositoryError, ValueError)):
        writer.create(Memory('new'), **command('new'))
    assert hashes(tmp_path) == before


def test_index_requires_locks_and_status_never_writes(tmp_path, monkeypatch, capsys):
    from core.information import cli
    monkeypatch.setattr(cli, 'HISTORY_ROOT', tmp_path / 'memory/history')
    monkeypatch.setattr(cli, 'check_environment', lambda *a: pytest.fail('status must not probe writes'))
    assert cli.main(['index-status']) == 0
    assert json.loads(capsys.readouterr().out)['status'] == 'DISABLED'
    assert list(tmp_path.iterdir()) == []
    writer = writer_at(tmp_path)
    with pytest.raises(RuntimeError, match='locks'):
        index_for(writer).refresh()


@pytest.mark.parametrize('boundary', ['event', 'commit'])
def test_index_left_behind_by_process_exit_refreshes_on_batch_replay(tmp_path, boundary):
    writer = writer_at(tmp_path)
    writer.rebuild_reservation_index()
    child = multiprocessing.get_context('spawn').Process(target=crash, args=(str(tmp_path), boundary))
    child.start(); child.join(15)
    try:
        assert child.exitcode == 74
    finally:
        if child.is_alive(): child.terminate(); child.join()
    assert writer.execute_batch([create('one'), create('two'), create('three')])['status'] == 'COMPLETED'
    assert check_readiness(tmp_path)['ready']
    assert len(list(writer.events.events_root.glob('*.md'))) == 3


def test_index_refresh_failure_precedes_command_and_next_attempt_rebuilds(tmp_path, monkeypatch):
    import core.information.reservation_index as module
    writer = writer_at(tmp_path)
    writer.rebuild_reservation_index()
    writer.create(Memory('old'), **command('old'))
    old = index_for(writer).path.read_bytes()
    with monkeypatch.context() as patch:
        patch.setattr(module, 'atomic_write_text', lambda *a: (_ for _ in ()).throw(OSError('disk failure')))
        with pytest.raises(OSError):
            writer.create(Memory('new'), **command('new'))
    assert index_for(writer).path.read_bytes() == old and writer.backend.get('new') is None
    writer.create(Memory('new'), **command('new'))
    assert check_readiness(tmp_path)['ready']


def test_other_process_pending_write_invalidates_old_index(tmp_path):
    writer = writer_at(tmp_path)
    writer.create(Memory('old'), **command('old'))
    writer.rebuild_reservation_index()
    child = multiprocessing.get_context('spawn').Process(target=create_pending_update, args=(str(tmp_path),))
    child.start(); join(child)
    with pytest.raises(OperationConflict, match='pending'):
        writer.update(writer.backend.get('old'), previous_revision=2, **command('other'))


def test_competing_indexed_batches_keep_one_event_owner(tmp_path):
    writer = writer_at(tmp_path)
    writer.rebuild_reservation_index()
    context = multiprocessing.get_context('spawn')
    start = context.Event(); ready = [context.Event(), context.Event()]
    children = [context.Process(target=competitor, args=(str(tmp_path), name, ready[i], start))
                for i, name in enumerate(['one', 'two'])]
    try:
        for child in children: child.start()
        assert all(event.wait(10) for event in ready)
        start.set()
        for child in children: join(child)
    finally:
        for child in children:
            if child.is_alive(): child.terminate(); child.join()
    results = [json.loads((tmp_path / (name + '.result')).read_text()) for name in ['one', 'two']]
    assert sorted(r['status'] for r in results) == ['BLOCKED', 'COMPLETED']
    assert len(writer.journal.ids()) == 2


def test_cli_rebuild_and_status(tmp_path):
    writer = writer_at(tmp_path)
    writer.create(Memory('old'), **command('old'))
    env = dict(os.environ, MEMORY_ENGINE_ROOT=str(tmp_path))
    args = [sys.executable, '-B', '-m', 'core.information.cli']
    result = subprocess.run(args + ['index-rebuild'], env=env, text=True, capture_output=True)
    assert result.returncode == 0 and json.loads(result.stdout)['validated'] == 1
    stable = hashes(tmp_path)
    result = subprocess.run(args + ['index-status'], env=env, text=True, capture_output=True)
    assert result.returncode == 0 and json.loads(result.stdout)['status'] == 'CURRENT'
    assert hashes(tmp_path) == stable


def exit_after_index_publication(root):
    import core.information.reservation_index as module
    original = module.atomic_write_text
    def publish(*args):
        original(*args)
        os._exit(74)
    module.atomic_write_text = publish
    writer_at(Path(root)).create(Memory('new'), **command('new'))


def test_process_exit_after_index_publication_before_command_is_replayable(tmp_path):
    writer = writer_at(tmp_path)
    writer.rebuild_reservation_index()
    writer.create(Memory('old'), **command('old'))
    child = multiprocessing.get_context('spawn').Process(target=exit_after_index_publication, args=(str(tmp_path),))
    child.start(); child.join(15)
    try:
        assert child.exitcode == 74
    finally:
        if child.is_alive(): child.terminate(); child.join()
    assert writer.backend.get('new') is None and index_for(writer).status()['status'] == 'CURRENT'
    writer.create(Memory('new'), **command('new'))
    assert check_readiness(tmp_path)['ready'] and len(writer.journal.ids()) == 2


def test_lifecycle_effects_use_index_with_same_canonical_revisions(tmp_path, monkeypatch):
    from core.lifecycle.service import LifecycleTriggers
    writer = writer_at(tmp_path)
    writer.execute_batch([create(str(i)) for i in range(5)])
    writer.rebuild_reservation_index()
    lifecycle = LifecycleTriggers(writer.backend)
    for i in range(5):
        lifecycle.schedule(str(i), revision=1, kind='RECHECK', due_at='2026-10-02T08:00:00Z',
                           trigger_id='wake-' + str(i), actor='human', created_at='2026-10-02T07:00:00Z')
    monkeypatch.setattr(InformationWriteJournal, 'reservations', lambda *a: pytest.fail('full reservation scan'))
    result = lifecycle.run_due(at='2026-10-02T08:00:00Z')
    assert len(result) == 5 and all(writer.backend.get(str(i)).revision == 2 for i in range(5))
    assert check_readiness(tmp_path)['ready']
