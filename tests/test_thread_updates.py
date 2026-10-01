"""Project mutations must compose with journals, deletion, and projections."""
from dataclasses import replace
import json

import pytest

from core.backend.filesystem import FilesystemBackend
from core.backend.models import Memory
from core.backend.errors import InformationDeletionBlocked
from core.dossiers.projects import ProjectDossiers, DossierConflict
from core.operations.errors import OperationConflict
from core.operations.models import OperationStatus
from core.operations.readiness import check_readiness, recover_all
from core.operations.thread_update import FilesystemThreadUpdates
from core.threads.models import Thread, ThreadStatus
from core.threads.storage import ThreadRevisionConflict
from core.threads.service import ThreadService

STAMP = '2026-10-01T17:30:00Z'


def seed(root):
    backend = FilesystemBackend(root / 'memory/persistent', root / 'memory/history')
    writer = FilesystemThreadUpdates(backend)
    for identity in ('one', 'two'):
        backend.store(Memory(identity, content='source ' + identity))
    writer.storage.create(Thread('project', 'Project', 'Objective',
                                relations=[{'type': 'CONCERNS', 'target_id': 'one'}],
                                created_at=STAMP, updated_at=STAMP))
    return backend, writer


def execute(writer, command, revision=1, opid='update'):
    return writer.execute('project', command, previous_revision=revision,
                          operation_id=opid, event_id='event-' + opid,
                          actor='human', timestamp=STAMP)


def test_second_information_and_actions_use_same_project_and_dossier(tmp_path):
    backend, writer = seed(tmp_path)
    command = {'kind': 'LINK', 'information_id': 'two'}
    linked = execute(writer, command)
    assert writer.storage._concerns(linked) == {'one', 'two'}
    action = {'kind': 'ADD_ACTION', 'action': {'action_id': 'a', 'description': 'Measure',
                                            'status': 'PLANNED', 'metadata': {}}}
    execute(writer, action, 2, 'add')
    result = execute(writer, {'kind': 'ACTION_STATUS', 'action_id': 'a', 'status': 'COMPLETED'}, 3, 'done')
    assert result.revision == 4 and result.actions[0].status.value == 'COMPLETED'
    assert execute(writer, command) == linked  # Original result, no extra write.
    dossier = ProjectDossiers(backend, writer.storage, tmp_path / 'dossiers')
    dossier.rebuild('project')
    text = (tmp_path / 'dossiers/project.md').read_text()
    assert 'source one' in text and 'source two' in text and 'COMPLETED' in text
    assert len(writer.storage.list()) == 1
    assert len(list(writer.events.events_root.glob('*.md'))) == 3


@pytest.mark.parametrize('boundary', ['prepared', 'applying', 'thread', 'event'])
def test_interruption_is_in_readiness_and_recovered_without_double_effect(tmp_path, monkeypatch, boundary):
    backend, writer = seed(tmp_path)
    with monkeypatch.context() as patch:
        if boundary == 'prepared':
            patch.setattr(writer, '_resume', lambda operation: (_ for _ in ()).throw(RuntimeError('stop')))
        elif boundary == 'applying':
            patch.setattr(writer.storage, '_update_coordinated', lambda *a: (_ for _ in ()).throw(RuntimeError('stop')))
        elif boundary == 'thread':
            patch.setattr(writer.events, 'save', lambda event: (_ for _ in ()).throw(RuntimeError('stop')))
        else:
            original = writer.operations.update
            def stop_commit(record):
                if record.status is OperationStatus.COMMITTED:
                    raise RuntimeError('stop')
                return original(record)
            patch.setattr(writer.operations, 'update', stop_commit)
        with pytest.raises(RuntimeError, match='stop'):
            execute(writer, {'kind': 'LINK', 'information_id': 'two'})
    assert not check_readiness(tmp_path)['ready']
    backend.delete_request('two', 'human', 'test', 1, 'delete-two')
    with pytest.raises(InformationDeletionBlocked):
        backend.approve_delete('two', 'delete-two')
    assert recover_all(tmp_path)['readiness']['ready']
    result = execute(writer, {'kind': 'LINK', 'information_id': 'two'})
    assert result.revision == 2 and writer.storage.get('project') == result
    assert len(list(writer.events.events_root.glob('*.md'))) == 1


def test_pending_mutation_blocks_status_thread_delete_and_dossier(tmp_path, monkeypatch):
    backend, writer = seed(tmp_path)
    service = ThreadService.for_backend(backend)
    dossier = ProjectDossiers(backend, writer.storage, tmp_path / 'dossiers')
    with monkeypatch.context() as patch:
        patch.setattr(writer, '_resume', lambda op: (_ for _ in ()).throw(RuntimeError('stop')))
        with pytest.raises(RuntimeError):
            execute(writer, {'kind': 'LINK', 'information_id': 'two'})
    with pytest.raises(OperationConflict):
        service.change_status('project', ThreadStatus.VALIDATED, previous_revision=1,
                              operation_id='status', event_id='status-event')
    with pytest.raises(OperationConflict):
        writer.storage.delete('project', previous_revision=1, operation_id='delete')
    with pytest.raises(DossierConflict):
        dossier.rebuild('project')


def test_unlink_then_delete_information_and_replay_never_resurrects(tmp_path):
    backend, writer = seed(tmp_path)
    command = {'kind': 'UNLINK', 'information_id': 'one'}
    removed = execute(writer, command)
    backend.delete_request('one', 'human', 'test', 1, 'delete-one')
    backend.approve_delete('one', 'delete-one')
    writer.storage.delete('project', previous_revision=2, operation_id='delete-thread')
    assert execute(writer, command) == removed
    assert writer.storage.get('project') is None and backend.get('one') is None


def test_stale_revision_changed_intent_and_event_reuse_are_rejected(tmp_path):
    _, writer = seed(tmp_path)
    execute(writer, {'kind': 'LINK', 'information_id': 'two'})
    with pytest.raises(OperationConflict):
        execute(writer, {'kind': 'UNLINK', 'information_id': 'two'})
    with pytest.raises(ThreadRevisionConflict):
        execute(writer, {'kind': 'UNLINK', 'information_id': 'two'}, 1, 'stale')
    with pytest.raises(OperationConflict):
        writer.execute('project', {'kind': 'UNLINK', 'information_id': 'two'}, previous_revision=2,
                       operation_id='collision', event_id='event-update', actor='human', timestamp=STAMP)


def test_failed_update_and_unknown_fields_fail_closed(tmp_path, monkeypatch):
    _, writer = seed(tmp_path)
    with pytest.raises(ValueError):
        execute(writer, {'kind': 'LINK', 'information_id': 'two', 'silent': True})
    with monkeypatch.context() as patch:
        patch.setattr(writer, '_resume', lambda op: (_ for _ in ()).throw(RuntimeError('stop')))
        with pytest.raises(RuntimeError):
            execute(writer, {'kind': 'LINK', 'information_id': 'two'})
    writer.operations.update(replace(writer.operations.get('update'), status=OperationStatus.FAILED))
    assert writer.recover()['update']['status'] == 'BLOCKED'
    assert not recover_all(tmp_path)['readiness']['ready']


def test_details_command_and_service_share_canonical_journals(tmp_path):
    backend, writer = seed(tmp_path)
    service = ThreadService.for_backend(backend)
    result = service.update_thread('project', {'kind': 'DETAILS', 'fields': {'objective': 'New objective',
                                                                        'context': {'place': 'lab'}}},
                                   previous_revision=1, operation_id='details', event_id='details-event',
                                   actor='human', timestamp=STAMP)
    assert result.objective == 'New objective' and result.context == {'place': 'lab'}
    assert writer.storage.get('project') == result
    assert check_readiness(tmp_path)['ready']


def test_link_refuses_pending_information_write_and_prior_delete_request(tmp_path, monkeypatch):
    from core.information.writes import FilesystemInformationWrites
    backend, writer = seed(tmp_path)
    writes = FilesystemInformationWrites(backend)
    with monkeypatch.context() as patch:
        patch.setattr(writes, '_resume', lambda *args: (_ for _ in ()).throw(RuntimeError('stop')))
        with pytest.raises(RuntimeError):
            writes.update(Memory('two', content='changed'), previous_revision=1, operation_id='info-update',
                          event_id='info-event', actor='human', timestamp=STAMP)
    with pytest.raises(InformationDeletionBlocked):
        execute(writer, {'kind': 'LINK', 'information_id': 'two'})
    assert not list(writer.operations.root.glob('*.json'))
    writes.recover()
    backend.delete_request('two', 'human', 'test', 2, 'delete-two')
    with pytest.raises(OperationConflict):
        execute(writer, {'kind': 'LINK', 'information_id': 'two'})
    assert not list(writer.operations.root.glob('*.json'))


def test_thread_status_pending_blocks_update_and_diverged_snapshot_is_preserved(tmp_path, monkeypatch):
    backend, writer = seed(tmp_path)
    service = ThreadService.for_backend(backend)
    with monkeypatch.context() as patch:
        patch.setattr(service.operations, '_resume', lambda op: (_ for _ in ()).throw(RuntimeError('stop')))
        with pytest.raises(RuntimeError):
            service.change_status('project', ThreadStatus.VALIDATED, previous_revision=1,
                                  operation_id='status', event_id='status-event')
    with pytest.raises(OperationConflict):
        execute(writer, {'kind': 'LINK', 'information_id': 'two'})
    service.operations.recover()
    with monkeypatch.context() as patch:
        patch.setattr(writer, '_resume', lambda op: (_ for _ in ()).throw(RuntimeError('stop')))
        with pytest.raises(RuntimeError):
            execute(writer, {'kind': 'LINK', 'information_id': 'two'}, 2)
    before = writer.storage.get('project')
    divergent = replace(before, objective='external change', revision=3)
    writer.storage.update(divergent, 2)
    assert writer.recover()['update']['status'] == 'BLOCKED'
    assert writer.storage.get('project') == divergent


def test_updated_thread_event_contract_and_legacy_guard(tmp_path):
    from core.events.models import Event, EventType
    from core.events.validator import validate_event
    from core.migration.legacy_guard import require_legacy_persistent_only
    backend, writer = seed(tmp_path)
    execute(writer, {'kind': 'UNLINK', 'information_id': 'one'})
    assert not validate_event(writer.events.get('event-update'))
    assert validate_event(Event('bad', 2, EventType.UPDATED, thread_id='project'))
    # The update journal alone still prevents a legacy writer from taking over.
    for path in backend.persistent_root.rglob('*.md'):
        path.unlink()
    with pytest.raises(ValueError, match='core operation journal'):
        require_legacy_persistent_only(backend.persistent_root, backend.history_root)


def test_command_cli_and_replay(tmp_path, monkeypatch, capsys):
    from core.operations import cli
    backend, writer = seed(tmp_path)
    command = tmp_path / 'command.json'
    command.write_text(json.dumps({'kind': 'LINK', 'information_id': 'two'}))
    for name, value in [('ENGINE_ROOT', tmp_path), ('PERSISTENT_ROOT', backend.persistent_root),
                        ('HISTORY_ROOT', backend.history_root)]:
        monkeypatch.setattr(cli, name, value)
    monkeypatch.setattr('sys.argv', ['operations', 'update-thread', 'project', '--command-file', str(command),
                                    '--previous-revision', '1', '--operation-id', 'cli', '--event-id', 'cli-event',
                                    '--actor', 'human', '--timestamp', STAMP])
    assert cli.main() == 0
    first = json.loads(capsys.readouterr().out)
    assert cli.main() == 0
    assert json.loads(capsys.readouterr().out) == first
    assert writer.storage.get('project').revision == 2
