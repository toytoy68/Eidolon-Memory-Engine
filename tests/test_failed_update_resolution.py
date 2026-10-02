"""Human retry of project commands keeps original effects and dependency guards."""
from dataclasses import replace
import json
import subprocess
import sys

import pytest

from core.backend.errors import InformationDeletionBlocked
from core.operations.errors import OperationConflict
from core.operations.failed_resolution import (
    review_failed_thread, retry_failed_thread, retry_failed_status, main,
)
from core.operations.models import OperationStatus
from core.operations.readiness import check_readiness, recover_all
from core.operations.thread_status import plan_hash
from core.threads.models import ThreadAction
from core.threads.storage import ThreadStorageError
from tests.test_failed_status_resolution import business_files, seed as seed_status
from tests.test_migration_converter import fingerprints
from tests.test_thread_updates import seed as project_seed, execute, STAMP

FAMILY = 'thread-update-v1'
COMMANDS = [
    {'kind': 'LINK', 'information_id': 'two'},
    {'kind': 'UNLINK', 'information_id': 'one'},
    {'kind': 'ADD_ACTION', 'action': {'action_id': 'new', 'description': 'Measure',
                                    'status': 'PLANNED', 'metadata': {}}},
    {'kind': 'ACTION_STATUS', 'action_id': 'existing', 'status': 'COMPLETED'},
    {'kind': 'DETAILS', 'fields': {'title': 'Changed', 'objective': 'Measured goal',
                                 'context': {'scope': 'reviewed'}}},
]


def seed(root, monkeypatch, command=None, phase='before'):
    backend, engine = project_seed(root)
    thread = engine.storage.get('project')
    engine.storage._path('project').write_text(engine.storage._serialize_checked(
        replace(thread, actions=[ThreadAction('existing', 'First')])))
    def stop(*args, **kw):
        raise RuntimeError('stopped')
    with monkeypatch.context() as patch:
        if phase == 'before':
            patch.setattr(engine, '_resume', stop)
        elif phase == 'thread':
            patch.setattr(engine.events, 'save', stop)
        else:
            update = engine.operations.update
            def commit(record):
                if record.status is OperationStatus.COMMITTED:
                    stop()
                update(record)
            patch.setattr(engine.operations, 'update', commit)
        with pytest.raises(RuntimeError):
            execute(engine, command or COMMANDS[0])
    engine.operations.update(replace(engine.operations.get('update'), status=OperationStatus.FAILED))
    return backend, engine


def review(root):
    return review_failed_thread(root, 'update', family=FAMILY)


def retry(root, report, **kw):
    decision = dict(resolution_id='decision', actor='human', reason='Effects reviewed', timestamp=STAMP)
    decision.update(kw)
    return retry_failed_thread(root, report, **decision)


@pytest.mark.parametrize('command', COMMANDS, ids=lambda c: c['kind'])
@pytest.mark.parametrize('phase', ['before', 'thread', 'event'])
def test_original_command_retries_once_from_each_partial_effect(tmp_path, monkeypatch, command, phase):
    _, engine = seed(tmp_path, monkeypatch, command, phase)
    failed = engine.operations.get('update')
    before = fingerprints(tmp_path)
    report = review(tmp_path)
    assert fingerprints(tmp_path) == before
    assert report['command'] == command and report['action'] == 'RETRY_THREAD_UPDATE_V1'
    assert report['thread_state'] == ('BEFORE' if phase == 'before' else 'AFTER')
    assert report['event_state'] == ('MATCH' if phase == 'event' else 'ABSENT')
    result = retry(tmp_path, report)
    completed = engine.operations.get('update')
    assert completed.status is OperationStatus.COMMITTED
    assert completed.plan == failed.plan and completed.execution_plan_hash == failed.execution_plan_hash
    assert plan_hash(completed) == failed.execution_plan_hash
    assert engine.storage.get('project') == engine.storage._deserialize(failed.plan.after_state)
    event, = engine.events.list_for_target('project')
    assert event.state_transition.after['command'] == command['kind']
    entry, = completed.manual_resolutions
    assert entry['action'] == 'RETRY_THREAD_UPDATE_V1' and entry['actor'] == 'human'
    assert entry['failed_record_sha256'] == report['failed_record_sha256']
    assert check_readiness(tmp_path)['ready']
    after = fingerprints(tmp_path)
    assert retry(tmp_path, report) == result and result['revision'] == 2
    assert fingerprints(tmp_path) == after


@pytest.mark.parametrize('change', ['thread', 'event', 'event-before-thread', 'journal-bytes',
                                     'command', 'plan', 'missing-link', 'corrupt-link', 'unknown-journal'])
def test_stale_or_conflicting_review_never_authorizes(tmp_path, monkeypatch, change):
    backend, engine = seed(tmp_path, monkeypatch)
    report = review(tmp_path)
    operation = engine.operations.get('update')
    if change == 'thread':
        thread = engine.storage.get('project')
        engine.storage._path('project').write_text(engine.storage._serialize_checked(replace(thread, title='Foreign')))
    elif change in {'event', 'event-before-thread'}:
        before, after = engine._validated_states(operation)
        event = engine._event(operation, before, after)
        engine.events.save(replace(event, revision=99) if change == 'event' else event)
    elif change == 'journal-bytes':
        path = engine.operations._path('update'); path.write_text(path.read_text() + '\n')
    elif change == 'command':
        report['command'] = COMMANDS[-1]
    elif change == 'plan':
        changed = replace(operation, plan=replace(operation.plan, command=json.dumps(COMMANDS[-1])))
        engine.operations._write(replace(changed, execution_plan_hash=plan_hash(changed)), engine.operations._path('update'))
    elif change == 'missing-link':
        backend._path('two').unlink()
    elif change == 'corrupt-link':
        backend._path('two').write_text('corrupt')
    else:
        path = backend.history_root / 'operations/unknown-v1'; path.mkdir()
        (path / 'other.json').write_text('{}')
    before = business_files(tmp_path)
    with pytest.raises((OperationConflict, ThreadStorageError)):
        retry(tmp_path, report)
    assert business_files(tmp_path) == before
    failed = engine.operations.get('update')
    assert failed.status is OperationStatus.FAILED and failed.manual_resolutions == []


@pytest.mark.parametrize('phase', ['before', 'thread', 'event'])
def test_link_reservation_survives_failure_and_pending_delete(tmp_path, monkeypatch, phase):
    backend, engine = seed(tmp_path, monkeypatch, phase=phase)
    backend.delete_request('two', 'human', 'Later request', 1, 'delete-two')
    before = fingerprints(tmp_path)
    with pytest.raises(InformationDeletionBlocked):
        backend.approve_delete('two', 'delete-two')
    report = review(tmp_path)
    assert fingerprints(tmp_path) == before
    retry(tmp_path, report)
    with pytest.raises(InformationDeletionBlocked):
        backend.approve_delete('two', 'delete-two')
    assert backend.get('two') is not None
    assert 'two' in engine.storage._concerns(engine.storage.get('project'))


def test_unlink_retry_releases_reference_and_terminal_replay_cannot_resurrect(tmp_path, monkeypatch):
    backend, engine = seed(tmp_path, monkeypatch, COMMANDS[1])
    backend.delete_request('one', 'human', 'Remove', 1, 'delete-one')
    with pytest.raises(InformationDeletionBlocked):
        backend.approve_delete('one', 'delete-one')
    report = review(tmp_path); result = retry(tmp_path, report)
    backend.approve_delete('one', 'delete-one')
    engine.storage.delete('project', previous_revision=2, operation_id='delete-project')
    before = fingerprints(tmp_path)
    assert retry(tmp_path, report) == result
    assert fingerprints(tmp_path) == before
    assert backend.get('one') is None and engine.storage.get('project') is None


@pytest.mark.parametrize('boundary', ['before_authorization', 'after_authorization', 'after_commit'])
def test_real_exit_recovers_authorized_update_only(tmp_path, monkeypatch, boundary):
    _, engine = seed(tmp_path, monkeypatch)
    report = review(tmp_path)
    script = '''
import os, sys, json
import core.operations.failed_resolution as m
m._checkpoint = lambda stage: os._exit(74) if stage == sys.argv[3] else None
m.retry_failed_thread(sys.argv[1], json.loads(sys.argv[2]), resolution_id='decision', actor='human',
                      reason='Effects reviewed', timestamp='2026-10-01T17:30:00Z')
'''
    process = subprocess.run([sys.executable, '-B', '-c', script, str(tmp_path), json.dumps(report), boundary])
    assert process.returncode == 74
    record = engine.operations.get('update')
    if boundary == 'before_authorization':
        assert record.status is OperationStatus.FAILED and not record.manual_resolutions
        assert recover_all(tmp_path)['passes'] == 0
    else:
        assert len(record.manual_resolutions) == 1
        assert record.status is (OperationStatus.APPLYING if boundary == 'after_authorization' else OperationStatus.COMMITTED)
        assert recover_all(tmp_path)['readiness']['ready']
    assert retry(tmp_path, report)['revision'] == 2
    assert len(engine.operations.get('update').manual_resolutions) == 1


@pytest.mark.parametrize('collision', ['thread', 'event', 'operation-id'])
def test_journal_reservations_are_checked_before_authorization(tmp_path, monkeypatch, collision):
    _, engine = seed(tmp_path, monkeypatch)
    report = review(tmp_path)
    if collision == 'operation-id':
        other = seed_status(tmp_path, monkeypatch, identity='another', opid='update')
        # Even a committed other-family ID must retain the coordinator's guard.
        record = other.operations.get('update')
        other.operations._write(replace(record, status=OperationStatus.COMMITTED), other.operations._path('update'))
    else:
        record = engine.operations.get('update')
        if collision == 'event':
            other_before = replace(engine.storage._deserialize(record.plan.before_state), thread_id='another')
            other_after = replace(engine.storage._deserialize(record.plan.after_state), thread_id='another')
            engine.storage.create(other_before)
            record = replace(record, target_id='another', plan=replace(record.plan,
                before_state=engine.storage._serialize_checked(other_before), after_state=engine.storage._serialize_checked(other_after)))
        else:
            record = replace(record, plan=replace(record.plan, event_id='other-event'))
        record = replace(record, operation_id='other')
        engine.operations.create(replace(record, execution_plan_hash=plan_hash(record)))
    before = business_files(tmp_path)
    with pytest.raises(OperationConflict):
        retry(tmp_path, report)
    assert business_files(tmp_path) == before


def test_status_api_rejects_update_review_and_wrong_family_audit_blocks_readiness(tmp_path, monkeypatch):
    _, engine = seed(tmp_path, monkeypatch)
    report = review(tmp_path); before = fingerprints(tmp_path)
    with pytest.raises(ValueError):
        retry_failed_status(tmp_path, report, resolution_id='decision', actor='human', reason='Review', timestamp=STAMP)
    assert fingerprints(tmp_path) == before
    retry(tmp_path, report)
    path = engine.operations._path('update'); data = json.loads(path.read_text())
    data['manual_resolutions'][0]['action'] = 'RETRY_THREAD_STATUS_V1'
    path.write_text(json.dumps(data)); before = fingerprints(tmp_path)
    assert not check_readiness(tmp_path)['ready']
    assert recover_all(tmp_path)['passes'] == 0
    assert fingerprints(tmp_path) == before


def test_cli_update_family_and_missing_root_are_read_only(tmp_path, monkeypatch, capsys):
    missing = tmp_path / 'missing'
    assert main(['--root', str(missing), 'preview', 'update', '--family', FAMILY]) == 1
    assert not missing.exists()
    capsys.readouterr()
    seed(tmp_path, monkeypatch); before = fingerprints(tmp_path)
    assert main(['--root', str(tmp_path), 'preview', 'update', '--family', FAMILY]) == 0
    report = capsys.readouterr().out
    assert fingerprints(tmp_path) == before
    path = tmp_path / 'review.json'; path.write_text(report)
    assert main(['--root', str(tmp_path), 'retry', '--review', str(path), '--resolution-id', 'decision',
                 '--actor', 'human', '--reason', 'Effects reviewed', '--timestamp', STAMP]) == 0
    assert json.loads(capsys.readouterr().out)['status'] == 'COMMITTED'
