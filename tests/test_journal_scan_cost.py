"""I/O reduction must preserve fresh reservations and strict journal validation."""
from collections import Counter
from dataclasses import replace
import json
import multiprocessing
from pathlib import Path

import pytest

from core.backend.filesystem import FilesystemBackend
from core.backend.models import Memory
from core.information.writes import FilesystemInformationWrites
from core.operations.errors import OperationConflict
from tools.vm_acceptance import hashes


def writer_at(root):
    return FilesystemInformationWrites(FilesystemBackend(root / 'memory/persistent', root / 'memory/history'))


def command(identity, event=None):
    return dict(operation_id='op-' + identity, event_id=event or 'event-' + identity,
                actor='human', timestamp='2026-10-01T20:00:00Z')


@pytest.mark.parametrize('compacted', [False, True])
def test_one_validated_read_of_each_prior_entry_per_new_command(tmp_path, monkeypatch, compacted):
    writer = writer_at(tmp_path)
    for i in range(8):
        writer.create(Memory(str(i), content='secret'), **command(str(i)))
        if compacted:
            writer.compact('op-' + str(i))
    read, ids = writer.journal.read, writer.journal.ids
    reads, scans = Counter(), []
    def observed_read(identity):
        reads[identity] += 1
        return read(identity)
    def observed_ids():
        scans.append(True)
        return ids()
    monkeypatch.setattr(writer.journal, 'read', observed_read)
    monkeypatch.setattr(writer.journal, 'ids', observed_ids)
    writer.create(Memory('new', content='new'), **command('new'))
    assert len(scans) == 1
    assert all(reads['op-' + str(i)] == 1 for i in range(8))
    assert writer.backend.get('new').revision == 1


def test_new_command_revalidates_unknown_receipt_version_after_warm_use(tmp_path):
    writer = writer_at(tmp_path)
    writer.create(Memory('old', content='old'), **command('old'))
    writer.compact('op-old')
    writer.create(Memory('warm', content='warm'), **command('warm'))
    path = writer.journal.receipt_path('op-old')
    data = json.loads(path.read_text())
    path.write_text(json.dumps(dict(data, format_version=999)))
    before = hashes(tmp_path)
    with pytest.raises(OperationConflict, match='receipt'):
        writer.create(Memory('new', content='new'), **command('new'))
    assert hashes(tmp_path) == before
    assert writer.backend.get('new') is None


def test_divergent_dual_record_blocks_unrelated_new_command(tmp_path, monkeypatch):
    import core.information.compaction as module
    writer = writer_at(tmp_path)
    writer.create(Memory('old', content='old'), **command('old'))
    with monkeypatch.context() as patch:
        patch.setattr(module, 'durable_unlink', lambda path: (_ for _ in ()).throw(RuntimeError('stop')))
        with pytest.raises(RuntimeError):
            writer.compact('op-old')
    path = writer.journal.receipt_path('op-old')
    data = json.loads(path.read_text())
    path.write_text(json.dumps(dict(data, event_sha256='f' * 64)))
    before = hashes(tmp_path)
    with pytest.raises(OperationConflict, match='divergent'):
        writer.create(Memory('new', content='new'), **command('new'))
    assert hashes(tmp_path) == before


def test_receipt_event_reservation_survives_missing_event_and_new_writer(tmp_path):
    writer = writer_at(tmp_path)
    writer.create(Memory('old', content='old'), **command('old'))
    writer.compact('op-old')
    writer.events._path('event-old').unlink()
    restarted = writer_at(tmp_path)
    with pytest.raises(OperationConflict, match='reserved'):
        restarted.create(Memory('new', content='new'), **command('new', event='event-old'))
    assert restarted.backend.get('new') is None


def create_pending_update(root):
    writer = writer_at(Path(root))
    writer.events.save = lambda event: (_ for _ in ()).throw(RuntimeError('stop'))
    try:
        writer.update(replace(writer.backend.get('old'), content='pending'), previous_revision=1,
                      **command('pending'))
    except RuntimeError:
        return
    raise AssertionError('expected interruption')


def join(child):
    try:
        child.join(15)
        assert child.exitcode == 0
    finally:
        if child.is_alive():
            child.terminate()
            child.join()


def test_same_writer_observes_pending_reservation_created_by_another_process(tmp_path):
    writer = writer_at(tmp_path)
    writer.create(Memory('old', content='initial'), **command('old'))
    child = multiprocessing.get_context('spawn').Process(target=create_pending_update, args=(str(tmp_path),))
    child.start()
    join(child)
    current = writer.backend.get('old')
    assert current.revision == 2
    with pytest.raises(OperationConflict, match='pending'):
        writer.update(replace(current, content='overwritten'), previous_revision=2, **command('other'))
    writer.resume('op-pending')
    assert writer.update(replace(current, content='after recovery'), previous_revision=2,
                         **command('other'))['revision'] == 3


def competitor(root, identity, ready, start):
    writer = writer_at(Path(root))
    ready.set()
    if not start.wait(10):
        raise RuntimeError('start timeout')
    try:
        writer.create(Memory(identity, content='racing'), **command(identity, event='shared-event'))
        result = 'COMMITTED'
    except OperationConflict:
        result = 'CONFLICT'
    (Path(root) / (identity + '.result')).write_text(result)


def test_concurrent_event_reservation_has_exactly_one_winner(tmp_path):
    writer = writer_at(tmp_path)
    context = multiprocessing.get_context('spawn')
    start = context.Event()
    ready = [context.Event(), context.Event()]
    children = [context.Process(target=competitor, args=(str(tmp_path), identity, ready[i], start))
                for i, identity in enumerate(('one', 'two'))]
    try:
        for child in children:
            child.start()
        assert all(event.wait(10) for event in ready)
        start.set()
        for child in children:
            join(child)
    finally:
        for child in children:
            if child.is_alive():
                child.terminate()
                child.join()
    assert sorted((tmp_path / (i + '.result')).read_text() for i in ('one', 'two')) == ['COMMITTED', 'CONFLICT']
    assert sum(writer.backend.get(i) is not None for i in ('one', 'two')) == 1
    assert len(writer.journal.ids()) == 1


def test_recovery_rebuilds_reservations_after_interruption(tmp_path, monkeypatch):
    writer = writer_at(tmp_path)
    original = writer.operations.create
    def stop(operation):
        original(operation)
        raise RuntimeError('stop')
    with monkeypatch.context() as patch:
        patch.setattr(writer.operations, 'create', stop)
        with pytest.raises(RuntimeError):
            writer.create(Memory('new', content='new'), **command('new'))
    assert writer.resume('op-new')['revision'] == 1
    writer.compact('op-new')
    before = hashes(tmp_path)
    assert writer.create(Memory('new', content='new'), **command('new'))['revision'] == 1
    assert hashes(tmp_path) == before
