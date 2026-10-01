"""First complete qualified Information → existing project → dossier journey."""
from dataclasses import replace
import json

import pytest

from core.backend.filesystem import FilesystemBackend
from core.backend.models import Memory
from core.backend.errors import InformationDeletionBlocked
from core.information.writes import FilesystemInformationWrites
from core.operations.errors import OperationConflict
from core.operations.readiness import check_readiness, recover_all
from core.routing.execution import RoutingExecutor
from core.routing.policy import RoutingContext, TargetRevision
from core.threads.models import Thread, ThreadStatus
from core.threads.service import ThreadService
from tests.test_migration_converter import fingerprints

STAMP = '2026-10-01T18:30:00Z'


def seed(root):
    backend = FilesystemBackend(root / 'memory/persistent', root / 'memory/history')
    service = ThreadService.for_backend(backend)
    backend.store(Memory('initial', content='first source'))
    service.create_linked(Thread('project', 'Project', 'Goal', created_at=STAMP, updated_at=STAMP),
                          'initial', operation_id='create-project', event_id='create-project-event')
    memory = Memory('second', content='measure 200 W', metadata={
        'type': 'OBSERVATION', 'epistemic_status': 'UNVERIFIED',
        'qualification': {'version': '0.1', 'nature': 'TECHNICAL', 'qualified_by': 'human'},
        'context': {'project_id': 'project', 'scope': {'goal': 'efficiency'}}},
        provenance={'source': 'bench'}, temporal={'observed_at': STAMP})
    return backend, RoutingExecutor(backend), memory


def preview(executor, memory, revision=1, **kwargs):
    return executor.preview(memory, RoutingContext(query_scope={'goal': 'efficiency'}, **kwargs),
                            project_revision=revision)


def execute(executor, prepared, intent='intent'):
    return executor.execute(prepared, intent_id=intent, actor='human', timestamp=STAMP)


def test_preview_no_writes_then_execution_and_terminal_replay(tmp_path):
    backend, executor, memory = seed(tmp_path)
    before = fingerprints(tmp_path)
    prepared = preview(executor, memory)
    assert fingerprints(tmp_path) == before
    result = execute(executor, prepared)
    assert backend.get('second') == memory
    assert executor.storage.get('project').revision == 2
    assert executor.dossiers.status('project')['status'] == 'CURRENT'
    assert result['information']['revision'] == 1 and result['project']['revision'] == 2
    assert result['deferred'] == ['availability']
    after = fingerprints(tmp_path)
    assert execute(executor, prepared) == result
    assert fingerprints(tmp_path) == after
    receipt = json.loads(executor.journal.path('intent').read_text())
    assert 'command' not in receipt and 'measure 200 W' not in json.dumps(receipt)


@pytest.mark.parametrize('boundary', ['before_information', 'after_information', 'after_project', 'after_projection'])
def test_interrupted_journey_is_globally_recoverable_and_reserved(tmp_path, monkeypatch, boundary):
    backend, executor, memory = seed(tmp_path)
    prepared = preview(executor, memory)
    def stop(stage):
        if stage == boundary:
            raise RuntimeError('stop')
    with monkeypatch.context() as patch:
        patch.setattr(executor, '_checkpoint', stop)
        with pytest.raises(RuntimeError, match='stop'):
            execute(executor, prepared)
    assert not check_readiness(tmp_path)['ready']
    service = ThreadService.for_backend(backend)
    with pytest.raises(OperationConflict):
        service.change_status('project', ThreadStatus.VALIDATED, previous_revision=executor.storage.get('project').revision,
                              operation_id='status', event_id='status-event')
    if backend.get('second') is not None:
        with pytest.raises(InformationDeletionBlocked):
            backend.delete_request('second', 'human', 'test', 1, 'delete-second')
    assert recover_all(tmp_path)['readiness']['ready']
    assert execute(executor, prepared)['project']['revision'] == 2
    assert executor.storage.get('project').revision == 2
    assert executor.dossiers.status('project')['status'] == 'CURRENT'


def test_update_plan_propagates_correction_and_preserves_notes(tmp_path):
    backend, executor, memory = seed(tmp_path)
    execute(executor, preview(executor, memory))
    path = executor.dossiers._path('project')
    path.write_text(path.read_text() + '\nHuman note.\n')
    edited = replace(memory, content='measure corrected 210 W')
    prepared = preview(executor, edited, 2, update_target=TargetRevision('second', 1))
    result = execute(executor, prepared, 'correction')
    assert result['information']['revision'] == 2
    assert executor.storage.get('project').revision == 2  # already linked, no extra mutation
    assert 'measure corrected 210 W' in path.read_text() and 'Human note.' in path.read_text()


@pytest.mark.parametrize('target', ['information', 'project'])
def test_stale_plan_is_refused_before_new_journal_or_business_write(tmp_path, target):
    backend, executor, memory = seed(tmp_path)
    if target == 'information':
        backend.store(memory)
        prepared = preview(executor, replace(memory, content='proposed'), update_target=TargetRevision('second', 1))
        backend.update('second', replace(memory, content='external'), previous_revision=1)
    else:
        prepared = preview(executor, memory)
        service = ThreadService.for_backend(backend)
        service.change_status('project', ThreadStatus.VALIDATED, previous_revision=1,
                              operation_id='status', event_id='status-event')
    before = fingerprints(tmp_path)
    with pytest.raises(OperationConflict):
        execute(executor, prepared)
    assert not executor.journal.path('intent').exists()
    # Lock inodes may be initialized, but no entity or journal can be written.
    assert {k:v for k,v in fingerprints(tmp_path).items() if not k.endswith('.write.lock')} == {
        k:v for k,v in before.items() if not k.endswith('.write.lock')}


def test_review_new_project_and_trigger_are_not_silently_executed(tmp_path):
    backend, executor, memory = seed(tmp_path)
    for unsupported in [replace(memory, metadata={}), replace(memory, temporal={'resume_at':STAMP}),
                        replace(memory, metadata=dict(memory.metadata, context={'project_id': 'missing'}))]:
        with pytest.raises(OperationConflict):
            preview(executor, unsupported)
    assert backend.get('second') is None


def test_changed_intention_and_deleted_terminal_targets_do_not_recreate(tmp_path):
    backend, executor, memory = seed(tmp_path)
    prepared = preview(executor, memory)
    result = execute(executor, prepared)
    changed = json.loads(json.dumps(prepared))
    changed['memory']['content'] = 'different'
    with pytest.raises(OperationConflict):
        execute(executor, changed)
    executor.storage.delete('project', previous_revision=2, operation_id='delete-project')
    writes = FilesystemInformationWrites(backend)
    writes.compact(executor.child_id('intent', 'information'))
    backend.delete_request('second', 'human', 'test', 1, 'delete-second')
    backend.approve_delete('second', 'delete-second')
    assert execute(executor, prepared) == result
    assert backend.get('second') is None and executor.storage.get('project') is None


def test_corrupt_journey_blocks_startup_without_writes(tmp_path):
    _, executor, _ = seed(tmp_path)
    path = executor.journal.path('bad')
    path.parent.mkdir(parents=True)
    path.write_text('{bad')
    before = fingerprints(tmp_path)
    assert not recover_all(tmp_path)['readiness']['ready']
    assert fingerprints(tmp_path) == before


def test_cli_preview_execute_and_replay(tmp_path, capsys):
    from dataclasses import asdict
    from core.routing.execution_cli import main
    backend, executor, memory = seed(tmp_path)
    memory_file, context_file, plan_file = (tmp_path / name for name in ('input.json', 'context.json', 'plan.json'))
    memory_file.write_text(json.dumps(asdict(memory)))
    context_file.write_text(json.dumps({'query_scope': {'goal': 'efficiency'}}))
    before = {str(path.relative_to(tmp_path)) for path in tmp_path.rglob('*')}
    assert main(['--root', str(tmp_path), 'preview', '--memory', str(memory_file),
                 '--context', str(context_file), '--project-revision', '1']) == 0
    assert {str(path.relative_to(tmp_path)) for path in tmp_path.rglob('*')} == before
    plan_file.write_text(capsys.readouterr().out)
    args = ['--root', str(tmp_path), 'execute', '--plan', str(plan_file), '--intent-id', 'cli',
            '--actor', 'human', '--timestamp', STAMP]
    assert main(args) == 0
    first = json.loads(capsys.readouterr().out)
    assert main(args) == 0
    assert json.loads(capsys.readouterr().out) == first
    assert executor.dossiers.status('project')['status'] == 'CURRENT'


@pytest.mark.parametrize('boundary', ['information_child', 'project_child'])
def test_child_interruption_resumes_inside_owning_journey(tmp_path, monkeypatch, boundary):
    from core.operations.thread_update import FilesystemThreadUpdates
    backend, executor, memory = seed(tmp_path)
    prepared = preview(executor, memory)
    with monkeypatch.context() as patch:
        cls = FilesystemInformationWrites if boundary == 'information_child' else FilesystemThreadUpdates
        patch.setattr(cls, '_resume', lambda *args: (_ for _ in ()).throw(RuntimeError('child stop')))
        with pytest.raises(RuntimeError):
            execute(executor, prepared)
    assert not check_readiness(tmp_path)['ready']
    assert recover_all(tmp_path)['readiness']['ready']
    assert backend.get('second') == memory and executor.storage.get('project').revision == 2


def test_preexisting_child_conflict_does_not_leave_parent_intention(tmp_path, monkeypatch):
    backend, executor, memory = seed(tmp_path)
    prepared = preview(executor, memory)
    service = ThreadService.for_backend(backend)
    with monkeypatch.context() as patch:
        patch.setattr(service.operations, '_resume', lambda *args: (_ for _ in ()).throw(RuntimeError('stop')))
        with pytest.raises(RuntimeError):
            service.change_status('project', ThreadStatus.VALIDATED, previous_revision=1,
                                  operation_id='status', event_id='status-event')
    with pytest.raises(OperationConflict):
        execute(executor, prepared)
    assert not executor.journal.path('intent').exists() and backend.get('second') is None
