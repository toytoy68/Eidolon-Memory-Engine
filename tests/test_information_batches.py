"""Bounded ledgers preserve command identity, reservations and partial progress."""
from collections import Counter
from dataclasses import asdict, replace
import json
import multiprocessing
import os
from pathlib import Path
import subprocess
import sys

import pytest

from core.backend.models import Memory
from core.information.batch import MAX_BATCH_SIZE
from core.information.write_journal import InformationWriteJournal
from core.operations.errors import OperationConflict
from core.operations.readiness import check_readiness
from tests.test_journal_scan_cost import writer_at, command
from tools.vm_acceptance import hashes


def create(identity, *, event=None, content=None):
    return dict(kind='CREATE', memory=asdict(Memory(identity, content=content or ('Payload ' + identity))),
                **command(identity, event))


def update(identity, previous, text, opid):
    return dict(kind='UPDATE', memory=asdict(Memory(identity, revision=previous, content=text)),
                previous_revision=previous, **command(opid))


def test_create_then_updates_and_duplicate_replay_keep_one_effect_per_command(tmp_path):
    writer = writer_at(tmp_path)
    commands = [create('one'), update('one', 1, 'Corrected', 'edit'), create('two')]
    result = writer.execute_batch(commands)
    assert result['status'] == 'COMPLETED' and result['next_index'] == 3
    assert writer.backend.get('one').revision == 2 and writer.backend.get('one').content == 'Corrected'
    assert len(writer.journal.ids()) == 3 and len(list(writer.events.events_root.glob('*.md'))) == 3
    stable = hashes(tmp_path)
    assert writer.execute_batch(commands) == result and hashes(tmp_path) == stable
    assert commands[1]['memory']['revision'] == 1
    assert writer.execute_batch([create('two'), create('two')])['status'] == 'COMPLETED'
    assert hashes(tmp_path) == stable


@pytest.mark.parametrize('compacted', [False, True])
def test_each_historical_entry_is_validated_once_for_the_whole_lot(tmp_path, monkeypatch, compacted):
    writer = writer_at(tmp_path)
    for i in range(8):
        writer.create(Memory(str(i)), **command(str(i)))
        if compacted:
            writer.compact('op-' + str(i))
    read, ids = writer.journal.read, writer.journal.ids
    counts, scans = Counter(), []
    def tracked(identity):
        counts[identity] += 1
        return read(identity)
    def scan():
        scans.append(True)
        return ids()
    monkeypatch.setattr(writer.journal, 'read', tracked)
    monkeypatch.setattr(writer.journal, 'ids', scan)
    result = writer.execute_batch([create('new-' + str(i)) for i in range(12)])
    assert result['status'] == 'COMPLETED' and len(scans) == 1
    assert all(counts['op-' + str(i)] == 1 for i in range(8))
    assert all(writer.backend.get('new-' + str(i)).revision == 1 for i in range(12))


def test_event_reserved_by_earlier_member_even_if_event_file_is_removed(tmp_path, monkeypatch):
    writer = writer_at(tmp_path)
    execute = writer._execute
    def remove_event(*args, **kwargs):
        result = execute(*args, **kwargs)
        writer.events._path(result['event_id']).unlink()  # simulate a lost Event; journal must still reserve its ID
        return result
    monkeypatch.setattr(writer, '_execute', remove_event)
    result = writer.execute_batch([create('one', event='shared'), create('two', event='shared')])
    assert result['status'] == 'BLOCKED' and result['next_index'] == 1
    assert 'reserved' in result['error']['reason']
    assert writer.backend.get('one') is not None and writer.backend.get('two') is None


def test_pending_member_can_resume_then_release_its_target_for_the_next_member(tmp_path, monkeypatch):
    writer = writer_at(tmp_path)
    commands = [create('one'), update('one', 1, 'Second value', 'edit')]
    with monkeypatch.context() as patch:
        patch.setattr(writer.events, 'save', lambda *a: (_ for _ in ()).throw(RuntimeError('stop')))
        with pytest.raises(RuntimeError):
            writer.execute_batch(commands)
    assert writer.backend.get('one').revision == 1 and not check_readiness(tmp_path)['ready']
    result = writer.execute_batch(commands)
    assert result['status'] == 'COMPLETED' and writer.backend.get('one').revision == 2
    assert check_readiness(tmp_path)['ready']


def test_unrelated_pending_owner_and_failed_operation_still_reserve_target(tmp_path, monkeypatch):
    from core.operations.models import OperationStatus
    writer = writer_at(tmp_path)
    with monkeypatch.context() as patch:
        patch.setattr(writer.events, 'save', lambda *a: (_ for _ in ()).throw(RuntimeError('stop')))
        with pytest.raises(RuntimeError):
            writer.create(Memory('owned'), **command('pending'))
    op = writer.operations.get('op-pending')
    writer.operations.update(replace(op, status=OperationStatus.FAILED))
    result = writer.execute_batch([create('free'), update('owned', 1, 'Must not overwrite', 'other')])
    assert result['status'] == 'BLOCKED' and result['next_index'] == 1
    assert writer.backend.get('free') is not None and writer.backend.get('owned').content is None
    assert writer.operations.get('op-pending').status is OperationStatus.FAILED


@pytest.mark.parametrize('mutation', ['unknown_receipt', 'divergent_pair'])
def test_corrupt_history_blocks_whole_lot_before_any_member(tmp_path, monkeypatch, mutation):
    writer = writer_at(tmp_path)
    writer.create(Memory('old'), **command('old'))
    if mutation == 'divergent_pair':
        import core.information.compaction as compaction
        with monkeypatch.context() as patch:
            patch.setattr(compaction, 'durable_unlink', lambda *a: (_ for _ in ()).throw(RuntimeError('stop')))
            with pytest.raises(RuntimeError):
                writer.compact('op-old')
    else:
        writer.compact('op-old')
    path = writer.journal.receipt_path('op-old')
    data = json.loads(path.read_text())
    data.update(format_version=999) if mutation == 'unknown_receipt' else data.update(event_sha256='f' * 64)
    path.write_text(json.dumps(data))
    stable = hashes(tmp_path)
    result = writer.execute_batch([create('new'), create('newer')])
    assert result['status'] == 'BLOCKED' and result['next_index'] == 0
    assert hashes(tmp_path) == stable


def test_next_lot_reloads_receipts_instead_of_reusing_previous_ledger(tmp_path):
    writer = writer_at(tmp_path)
    assert writer.execute_batch([create('old')])['status'] == 'COMPLETED'
    writer.compact('op-old')
    path = writer.journal.receipt_path('op-old')
    data = json.loads(path.read_text()); data['format_version'] = 999
    path.write_text(json.dumps(data))
    assert writer.execute_batch([create('new')])['status'] == 'BLOCKED'
    assert writer.backend.get('new') is None


def test_compact_terminal_batch_replays_after_deletion_without_resurrection(tmp_path):
    writer = writer_at(tmp_path)
    commands = [create('one'), update('one', 1, 'Second', 'edit')]
    result = writer.execute_batch(commands)
    for entry in commands:
        writer.compact(entry['operation_id'])
    writer.backend.delete_request('one', 'human', 'remove', 2, 'delete')
    writer.backend.approve_delete('one', 'delete')
    stable = hashes(tmp_path)
    assert writer.execute_batch(commands) == result
    assert writer.backend.get('one') is None and hashes(tmp_path) == stable


def test_changed_command_id_stops_and_keeps_the_committed_prefix(tmp_path):
    writer = writer_at(tmp_path)
    commands = [create('one'), dict(create('two'), operation_id='op-one'), create('three')]
    result = writer.execute_batch(commands)
    assert result['status'] == 'BLOCKED' and result['next_index'] == 1
    assert len(result['results']) == 1 and writer.backend.get('one') is not None
    assert writer.backend.get('two') is None and writer.backend.get('three') is None
    commands[1]['operation_id'] = 'op-two'
    assert writer.execute_batch(commands)['status'] == 'COMPLETED'
    assert writer.backend.get('one').revision == 1 and len(writer.journal.ids()) == 3


@pytest.mark.parametrize('invalid', ['empty', 'oversized', 'bad_tail'])
def test_bounds_and_structural_errors_are_refused_before_the_first_effect(tmp_path, invalid):
    writer = writer_at(tmp_path)
    commands = [] if invalid == 'empty' else [create(str(i)) for i in range(MAX_BATCH_SIZE + 1)] if invalid == 'oversized' else [create('valid'), {'kind': 'wrong'}]
    before = hashes(tmp_path)
    with pytest.raises(ValueError):
        writer.execute_batch(commands)
    assert hashes(tmp_path) == before and writer.journal.ids() == []


def test_pending_deletion_blocks_only_at_its_member_without_approval(tmp_path):
    writer = writer_at(tmp_path)
    writer.create(Memory('old'), **command('old'))
    writer.backend.delete_request('old', 'human', 'later', 1, 'delete')
    result = writer.execute_batch([create('new'), update('old', 1, 'Not allowed', 'edit')])
    assert result['status'] == 'BLOCKED' and result['next_index'] == 1
    assert writer.backend.get('old').revision == 1
    assert json.loads((writer.backend.pending_delete_root / 'old.json').read_text())['status'] == 'PENDING_DELETE'


def crash(root, boundary):
    writer = writer_at(Path(root))
    original = writer.events.save if boundary == 'event' else writer.operations.update
    def stop(record):
        result = original(record)
        if (boundary == 'event' and record.event_id == 'event-two') or (
            boundary == 'commit' and record.operation_id == 'op-two' and record.status.value == 'COMMITTED'):
            os._exit(74)
        return result
    if boundary == 'event':
        writer.events.save = stop
    else:
        writer.operations.update = stop
    writer.execute_batch([create('one'), create('two'), create('three')])


@pytest.mark.parametrize('boundary', ['event', 'commit'])
def test_process_exit_mid_batch_replays_prefix_and_finishes_suffix(tmp_path, boundary):
    writer = writer_at(tmp_path)
    child = multiprocessing.get_context('spawn').Process(target=crash, args=(str(tmp_path), boundary))
    child.start()
    try:
        child.join(15)
        assert child.exitcode == 74
    finally:
        if child.is_alive():
            child.terminate(); child.join()
    assert writer.backend.get('three') is None
    result = writer.execute_batch([create('one'), create('two'), create('three')])
    assert result['status'] == 'COMPLETED' and check_readiness(tmp_path)['ready']
    assert all(writer.backend.get(i).revision == 1 for i in ['one', 'two', 'three'])
    assert len(list(writer.events.events_root.glob('*.md'))) == 3


def competitor(root, identity, ready, start):
    writer = writer_at(Path(root))
    ready.set()
    if not start.wait(10):
        raise RuntimeError('start timeout')
    result = writer.execute_batch([create(identity, event='shared'), create(identity + '-tail')])
    (Path(root) / (identity + '.result')).write_text(json.dumps(result))


def test_competing_batches_reserve_shared_event_before_any_losing_suffix(tmp_path):
    writer = writer_at(tmp_path)
    context = multiprocessing.get_context('spawn')
    start = context.Event(); ready = [context.Event(), context.Event()]
    children = [context.Process(target=competitor, args=(str(tmp_path), name, ready[i], start)) for i,name in enumerate(['one','two'])]
    try:
        for child in children: child.start()
        assert all(event.wait(10) for event in ready)
        start.set()
        for child in children:
            child.join(15); assert child.exitcode == 0
    finally:
        for child in children:
            if child.is_alive(): child.terminate(); child.join()
    reports = [json.loads((tmp_path / (name + '.result')).read_text()) for name in ['one','two']]
    assert sorted(r['status'] for r in reports) == ['BLOCKED', 'COMPLETED']
    assert len(writer.journal.ids()) == 2
    loser = ['one','two'][next(i for i,r in enumerate(reports) if r['status'] == 'BLOCKED')]
    assert writer.backend.get(loser + '-tail') is None


def test_cli_json_batch_and_replay_then_conflict_exit(tmp_path):
    writer_at(tmp_path)
    source = tmp_path / 'commands.json'
    source.write_text(json.dumps([create('one'), create('two')]))
    env = dict(os.environ, MEMORY_ENGINE_ROOT=str(tmp_path))
    cmd = [sys.executable, '-B', '-m', 'core.information.cli', 'batch', '--input', str(source)]
    first = subprocess.run(cmd, env=env, text=True, capture_output=True)
    assert first.returncode == 0, first.stderr
    second = subprocess.run(cmd, env=env, text=True, capture_output=True)
    assert second.returncode == 0 and json.loads(first.stdout) == json.loads(second.stdout)
    source.write_text(json.dumps([create('one', content='different')]))
    blocked = subprocess.run(cmd, env=env, text=True, capture_output=True)
    assert blocked.returncode == 1 and json.loads(blocked.stdout)['status'] == 'BLOCKED'


@pytest.mark.parametrize('lot_size,expected_scans', [(2, 3), (100, 1)])
def test_lifecycle_reuses_one_scan_per_bounded_lot(tmp_path, monkeypatch, lot_size, expected_scans):
    from core.lifecycle.service import LifecycleTriggers
    writer = writer_at(tmp_path)
    commands = [create(str(i)) for i in range(5)]
    writer.execute_batch(commands)
    lifecycle = LifecycleTriggers(writer.backend)
    for i in range(5):
        lifecycle.schedule(str(i), revision=1, kind='RECHECK', due_at='2026-10-02T08:00:00Z',
                           trigger_id='wake-' + str(i), actor='human', created_at='2026-10-02T07:00:00Z')
    calls = []
    original = InformationWriteJournal.reservations
    def tracked(self):
        calls.append(True)
        return original(self)
    monkeypatch.setattr(InformationWriteJournal, 'reservations', tracked)
    monkeypatch.setattr('core.information.batch.MAX_BATCH_SIZE', lot_size)
    result = lifecycle.run_due(at='2026-10-02T08:00:00Z')
    assert len(calls) == expected_scans and len(result) == 5
    assert all(writer.backend.get(str(i)).revision == 2 for i in range(5))
