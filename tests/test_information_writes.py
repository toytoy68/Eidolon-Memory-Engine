from dataclasses import replace
from contextlib import contextmanager
import json

import pytest

from core.backend.filesystem import FilesystemBackend
from core.backend.models import Memory
from core.backend.errors import InformationDeletionBlocked
from core.operations.errors import OperationConflict
from core.operations.models import OperationStatus
from core.information.writes import FilesystemInformationWrites


def service(tmp_path):
    return FilesystemInformationWrites(FilesystemBackend(
        tmp_path / 'memory/persistent', tmp_path / 'memory/history'))


def memory():
    return Memory('info-1', content='Texte privé à conserver exactement.',
                  metadata={'type': 'OBSERVATION', 'epistemic_status': 'CONFLICTED',
                            'extension': {'nested': [1, 'é']}},
                  verification={'method': 'legacy'}, temporal={'observed_at': 'yesterday'})


def command(kind='create'):
    return dict(operation_id=kind, event_id='event-' + kind,
                actor='toytoy', timestamp='2026-10-01T05:00:00Z')


def test_create_update_full_snapshot_and_content_free_events(tmp_path):
    writer = service(tmp_path)
    original = memory()
    result = writer.create(original, **command())
    assert result == {'information_id': 'info-1', 'previous_revision': 0,
                      'revision': 1, 'event_id': 'event-create'}
    edited = replace(original, content='Nouveau texte privé.')
    changed = writer.update(edited, previous_revision=1, **command('update'))
    assert changed['revision'] == 2
    assert writer.backend.get('info-1') == replace(edited, revision=2)
    assert original.revision == 1
    for opid, kind in [('create', 'CREATED'), ('update', 'UPDATED')]:
        op = writer.operations.get(opid)
        assert op.status is OperationStatus.COMMITTED
        event = writer.events.get('event-' + opid)
        assert event.event_type.value == kind
        assert event.provenance.actor == 'toytoy'
        text = writer.events._path(event.event_id).read_text()
        assert original.content not in text and edited.content not in text
        assert event.state_transition.after['content_sha256']
    assert writer.create(original, **command()) == result
    assert writer.backend.get('info-1').revision == 2


@pytest.mark.parametrize('kind', ['create', 'update'])
@pytest.mark.parametrize('stage', ['prepared', 'applying', 'memory', 'event', 'committed'])
def test_recover_every_write_boundary(tmp_path, monkeypatch, kind, stage):
    writer = service(tmp_path)
    target = memory()
    if kind == 'update':
        writer.create(target, **command('initial'))
        target = replace(target, content='Updated')
    if stage == 'prepared':
        obj, attr = writer.operations, 'create'
    elif stage in {'applying', 'committed'}:
        obj, attr = writer.operations, 'update'
    elif stage == 'memory':
        obj, attr = writer.backend, '_atomic_write'
    else:
        obj, attr = writer.events, 'save'
    real = getattr(obj, attr)

    def interrupted(*args, **kwargs):
        result = real(*args, **kwargs)
        if stage not in {'applying', 'committed'} or args[0].status.value == stage.upper():
            raise RuntimeError('interrupted')
        return result

    monkeypatch.setattr(obj, attr, interrupted)
    with pytest.raises(RuntimeError, match='interrupted'):
        if kind == 'create':
            writer.create(target, **command())
        else:
            writer.update(target, previous_revision=1, **command('update'))
    monkeypatch.setattr(obj, attr, real)
    restarted = service(tmp_path)
    restarted.recover()
    result = (restarted.create(target, **command()) if kind == 'create' else
              restarted.update(target, previous_revision=1, **command('update')))
    assert result['revision'] == (1 if kind == 'create' else 2)
    assert restarted.backend.get('info-1') == replace(target, revision=result['revision'])
    assert restarted.operations.get(kind).status is OperationStatus.COMMITTED
    assert len(list(restarted.events.events_root.glob('*.md'))) == (1 if kind == 'create' else 2)


def test_replay_distinguishes_command_fields(tmp_path):
    writer = service(tmp_path)
    writer.create(memory(), **command())
    for field, value in [('actor', 'other'), ('timestamp', 'later'), ('event_id', 'other')]:
        with pytest.raises(OperationConflict, match='different command'):
            writer.create(memory(), **(command() | {field: value}))
    with pytest.raises(OperationConflict, match='different command'):
        writer.create(replace(memory(), metadata={'extension': 'changed'}), **command())
    with pytest.raises(OperationConflict, match='different command'):
        writer.update(memory(), previous_revision=1, **command())


def test_pending_operation_blocks_other_writer_and_deletion(tmp_path, monkeypatch):
    writer = service(tmp_path)
    writer.create(memory(), **command())
    real = writer.events.save
    monkeypatch.setattr(writer.events, 'save', lambda event: (_ for _ in ()).throw(RuntimeError()))
    with pytest.raises(RuntimeError):
        writer.update(replace(memory(), content='new'), previous_revision=1, **command('pending'))
    with pytest.raises(OperationConflict, match='pending'):
        writer.update(replace(memory(), revision=2), previous_revision=2, **command('other'))
    with pytest.raises(InformationDeletionBlocked):
        writer.backend.delete_request('info-1', 'toytoy', 'cleanup', 2, 'delete')
    monkeypatch.setattr(writer.events, 'save', real)
    writer.resume('pending')
    writer.backend.delete_request('info-1', 'toytoy', 'cleanup', 2, 'delete')
    with pytest.raises(InformationDeletionBlocked, match='compact'):
        writer.backend.approve_delete('info-1', 'delete')


def test_cancel_then_update_is_two_separate_commands(tmp_path):
    writer = service(tmp_path)
    writer.create(memory(), **command())
    writer.backend.delete_request('info-1', 'toytoy', 'cleanup', 1, 'delete')
    with pytest.raises(OperationConflict, match='PENDING_DELETE'):
        writer.update(memory(), previous_revision=1, **command('update'))
    writer.backend.cancel_delete('info-1', 'delete')
    restarted = service(tmp_path)
    assert restarted.backend.get('info-1') == memory()
    assert json.loads((restarted.backend.pending_delete_root / 'info-1.json').read_text())['status'] == 'CANCELLED'
    assert restarted.update(memory(), previous_revision=1, **command('update'))['revision'] == 2


def test_divergent_target_or_event_blocks_recovery_without_overwrite(tmp_path, monkeypatch):
    writer = service(tmp_path)
    original = writer.operations.create
    def prepared(op):
        original(op)
        raise RuntimeError()
    monkeypatch.setattr(writer.operations, 'create', prepared)
    with pytest.raises(RuntimeError):
        writer.create(memory(), **command())
    writer.backend._atomic_write(writer.backend._path('info-1'),
                                writer.backend._serialize(replace(memory(), content='elsewhere')))
    before = writer.backend._path('info-1').read_bytes()
    assert writer.recover()['create']['status'] == 'BLOCKED'
    assert writer.backend._path('info-1').read_bytes() == before


def test_lock_acquisition_order(tmp_path, monkeypatch):
    import core.persistence as persistence
    writer = service(tmp_path)
    real = persistence._exclusive_write
    trace = []
    @contextmanager
    def traced(root):
        trace.append(root)
        with real(root):
            yield
    monkeypatch.setattr(persistence, '_exclusive_write', traced)
    writer.create(memory(), **command())
    assert trace == [writer.backend.persistent_root, writer.operations.root, writer.events.events_root]


def test_cli_create_update_and_recover_all(tmp_path):
    import os
    import subprocess
    import sys
    from dataclasses import asdict
    target = tmp_path / 'command.json'
    target.write_text(json.dumps(asdict(memory())))
    env = dict(os.environ, MEMORY_ENGINE_ROOT=str(tmp_path), PYTHONDONTWRITEBYTECODE='1')
    common = ['--input', str(target), '--actor', 'toytoy', '--timestamp', 'fixed']
    for name, extra in [('create', []), ('update', ['--previous-revision', '1'])]:
        result = subprocess.run([sys.executable, '-B', '-m', 'core.information.cli', name,
                                 *common, '--operation-id', name, '--event-id', 'event-' + name, *extra],
                                env=env, text=True, capture_output=True)
        assert result.returncode == 0, result.stderr
        assert json.loads(result.stdout)['revision'] == (1 if name == 'create' else 2)
    result = subprocess.run([sys.executable, '-B', '-m', 'core.operations.cli', 'recover-all'],
                            env=env, text=True, capture_output=True)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)['information-writes']['update']['status'] == 'COMMITTED'


def test_pending_incoming_relation_reserves_deletion_target(tmp_path, monkeypatch):
    writer = service(tmp_path)
    writer.backend.store(Memory('other', content='target'))
    real = writer.operations.create
    def prepared(op):
        real(op)
        raise RuntimeError()
    monkeypatch.setattr(writer.operations, 'create', prepared)
    with pytest.raises(RuntimeError):
        writer.create(replace(memory(), relations=[{'type': 'RELATED_TO', 'target': 'other'}]), **command())
    with pytest.raises(InformationDeletionBlocked, match='references'):
        writer.backend.delete_request('other', 'toytoy', 'cleanup', 1, 'delete')


def test_event_collision_checked_before_information_write(tmp_path):
    writer = service(tmp_path)
    writer.create(memory(), **command())
    with pytest.raises(OperationConflict, match='event_id'):
        writer.create(replace(memory(), information_id='other'), **(command() | {'operation_id': 'other'}))
    assert writer.backend.get('other') is None
    assert writer.operations.get('other') is None
