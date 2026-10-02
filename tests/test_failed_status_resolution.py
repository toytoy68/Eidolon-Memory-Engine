"""Explicit FAILED retry: audit and APPLYING appear together, then normal recovery."""
from dataclasses import replace
import json
from pathlib import Path
import subprocess
import sys

import pytest

from core.backend.filesystem import FilesystemBackend
from core.events.filesystem import FilesystemEventRepository
from core.operations.errors import OperationConflict, InvalidOperationRecord
from core.operations.failed_resolution import review_failed_status, retry_failed_status, main
from core.operations.filesystem import FilesystemOperationRepository
from core.operations.models import OperationStatus
from core.operations.readiness import check_readiness, recover_all
from core.operations.thread_status import FilesystemThreadOperations, plan_hash
from core.threads.models import Thread, ThreadStatus
from core.threads.storage import ThreadStorage
from tests.test_migration_converter import fingerprints

STAMP = '2026-10-02T14:30:00Z'


def seed(root, monkeypatch, phase='before', identity='project', opid='op'):
    backend = FilesystemBackend(root / 'memory/persistent', root / 'memory/history')
    engine = FilesystemThreadOperations(ThreadStorage(backend.persistent_root),
        FilesystemEventRepository(backend.history_root / 'events/thread-status-v1'),
        FilesystemOperationRepository(backend.history_root / 'operations/thread-status-v1'))
    engine.storage.create(Thread(identity, 'Project', 'Goal', created_at=STAMP, updated_at=STAMP))
    def stop(*a, **kw):
        raise RuntimeError('stopped')
    with monkeypatch.context() as patch:
        if phase == 'before':
            patch.setattr(engine, '_resume', stop)
        elif phase == 'thread':
            patch.setattr(engine.events, 'save', stop)
        elif phase == 'event':
            update = engine.operations.update
            def before_commit(record):
                if record.status is OperationStatus.COMMITTED:
                    stop()
                update(record)
            patch.setattr(engine.operations, 'update', before_commit)
        with pytest.raises(RuntimeError):
            engine.change_status(identity, ThreadStatus.VALIDATED, previous_revision=1,
                                 operation_id=opid, event_id='event-' + opid)
    operation = engine.operations.get(opid)
    engine.operations.update(replace(operation, status=OperationStatus.FAILED))
    return engine


def retry(root, review, **kw):
    args = dict(resolution_id='decision', actor='human', reason='reviewed matching snapshots', timestamp=STAMP)
    args.update(kw)
    return retry_failed_status(root, review, **args)


def business_files(root):
    return {k: v for k, v in fingerprints(root).items() if not k.endswith('.write.lock')}


@pytest.mark.parametrize('phase,state,event', [('before','BEFORE','ABSENT'), ('thread','AFTER','ABSENT'), ('event','AFTER','MATCH')])
def test_review_retry_and_replay_preserve_identity_revision_event_and_audit(tmp_path, monkeypatch, phase, state, event):
    engine = seed(tmp_path, monkeypatch, phase)
    failed = engine.operations.get('op')
    before = fingerprints(tmp_path)
    review = review_failed_status(tmp_path, 'op')
    assert fingerprints(tmp_path) == before
    assert (review['thread_state'], review['event_state']) == (state, event)
    assert not check_readiness(tmp_path)['ready']
    assert recover_all(tmp_path)['passes'] == 0
    result = retry(tmp_path, review)
    assert result == dict(status='COMMITTED', resolution_id='decision', operation_id='op', thread_id='project', revision=2)
    completed = engine.operations.get('op')
    assert completed.status is OperationStatus.COMMITTED
    assert completed.plan == failed.plan and completed.execution_plan_hash == failed.execution_plan_hash
    assert plan_hash(completed) == completed.execution_plan_hash
    entry, = completed.manual_resolutions
    assert entry['actor'] == 'human' and entry['reason'] == 'reviewed matching snapshots'
    assert entry['failed_record_sha256'] == review['failed_record_sha256']
    assert engine.storage.get('project').revision == 2
    assert len(engine.events.list_for_target('project')) == 1
    assert check_readiness(tmp_path)['ready']
    after = fingerprints(tmp_path)
    assert retry(tmp_path, review) == result
    assert fingerprints(tmp_path) == after


@pytest.mark.parametrize('boundary', ['before_authorization', 'after_authorization', 'after_commit'])
def test_interruption_keeps_failed_or_audited_applying_then_global_recovery(tmp_path, monkeypatch, boundary):
    import core.operations.failed_resolution as module
    engine = seed(tmp_path, monkeypatch)
    review = review_failed_status(tmp_path, 'op')
    def stop(stage):
        if stage == boundary:
            raise RuntimeError('interrupted')
    with monkeypatch.context() as patch:
        patch.setattr(module, '_checkpoint', stop)
        with pytest.raises(RuntimeError):
            retry(tmp_path, review)
    record = engine.operations.get('op')
    if boundary == 'before_authorization':
        assert record.status is OperationStatus.FAILED and record.manual_resolutions == []
        assert not recover_all(tmp_path)['readiness']['ready']
    else:
        assert len(record.manual_resolutions) == 1
        assert record.status is (OperationStatus.APPLYING if boundary == 'after_authorization' else OperationStatus.COMMITTED)
        assert recover_all(tmp_path)['readiness']['ready']
    assert retry(tmp_path, review)['status'] == 'COMMITTED'
    assert len(engine.operations.get('op').manual_resolutions) == 1


@pytest.mark.parametrize('change', ['thread', 'event', 'plan', 'journal-bytes', 'other-journal', 'forged-review'])
def test_changed_review_or_divergent_effect_is_blocked_without_reopening(tmp_path, monkeypatch, change):
    engine = seed(tmp_path, monkeypatch)
    review = review_failed_status(tmp_path, 'op')
    if change == 'thread':
        thread = engine.storage.get('project')
        engine.storage._path('project').write_text(engine.storage._serialize_checked(replace(thread, title='foreign')))
    elif change == 'event':
        op = engine.operations.get('op')
        before, after = engine._validated_states(op)
        engine.events.save(replace(engine._event(op, before, after), revision=99))
    elif change == 'plan':
        path = engine.operations._path('op')
        raw = json.loads(path.read_text()); raw['execution_plan_hash'] = '0' * 64
        path.write_text(json.dumps(raw))
    elif change == 'journal-bytes':
        path = engine.operations._path('op'); path.write_text(path.read_text() + '\n')
    elif change == 'other-journal':
        path = tmp_path / 'memory/history/operations/unknown-v1'
        path.mkdir(); (path / 'unknown.json').write_text('{}')
    else:
        review['write_thread'] = False
    before = business_files(tmp_path)
    with pytest.raises((OperationConflict, InvalidOperationRecord)):
        retry(tmp_path, review)
    assert business_files(tmp_path) == before
    assert engine.operations.get('op').status is OperationStatus.FAILED


def test_event_without_after_snapshot_is_not_accepted_as_partial_success(tmp_path, monkeypatch):
    engine = seed(tmp_path, monkeypatch, phase='event')
    operation = engine.operations.get('op')
    engine.storage._path('project').write_text(operation.plan.before_state)
    before = fingerprints(tmp_path)
    with pytest.raises(OperationConflict, match='Event exists'):
        review_failed_status(tmp_path, 'op')
    assert fingerprints(tmp_path) == before


@pytest.mark.parametrize('field,value', [('actor',''), ('reason',' '), ('timestamp','invalid'), ('timestamp','2026-10-02T14:30:00'), ('resolution_id','../bad')])
def test_human_decision_metadata_is_required_before_writes(tmp_path, monkeypatch, field, value):
    seed(tmp_path, monkeypatch)
    review = review_failed_status(tmp_path, 'op')
    before = fingerprints(tmp_path)
    with pytest.raises((ValueError, InvalidOperationRecord)):
        retry(tmp_path, review, **{field:value})
    assert fingerprints(tmp_path) == before


def test_generic_repository_cannot_reopen_failed_or_modify_authorization(tmp_path, monkeypatch):
    import core.operations.failed_resolution as module
    engine = seed(tmp_path, monkeypatch)
    record = engine.operations.get('op')
    with pytest.raises(ValueError):
        engine.operations.update(replace(record, status=OperationStatus.APPLYING))
    def stop(stage):
        if stage == 'after_authorization':
            raise RuntimeError('stopped')
    with monkeypatch.context() as patch:
        patch.setattr(module, '_checkpoint', stop)
        with pytest.raises(RuntimeError):
            retry(tmp_path, review_failed_status(tmp_path, 'op'))
    record = engine.operations.get('op')
    with pytest.raises(OperationConflict):
        engine.operations.update(replace(record, status=OperationStatus.COMMITTED, manual_resolutions=[]))


def test_terminal_replay_does_not_resurrect_deleted_thread_or_change_decision(tmp_path, monkeypatch):
    engine = seed(tmp_path, monkeypatch)
    review = review_failed_status(tmp_path, 'op')
    result = retry(tmp_path, review)
    engine.storage._path('project').unlink()
    before = fingerprints(tmp_path)
    assert retry(tmp_path, review) == result
    assert not engine.storage._path('project').exists()
    with pytest.raises(OperationConflict):
        retry(tmp_path, review, reason='different decision')
    assert fingerprints(tmp_path) == before


def test_independent_failed_changes_can_be_resolved_one_at_a_time(tmp_path, monkeypatch):
    seed(tmp_path, monkeypatch)
    seed(tmp_path, monkeypatch, identity='second', opid='second')
    retry(tmp_path, review_failed_status(tmp_path, 'op'))
    assert not check_readiness(tmp_path)['ready']
    retry(tmp_path, review_failed_status(tmp_path, 'second'), resolution_id='second-decision')
    assert check_readiness(tmp_path)['ready']


def test_cli_preview_retry_and_invalid_resolution_exit_codes(tmp_path, monkeypatch, capsys):
    seed(tmp_path, monkeypatch)
    before = fingerprints(tmp_path)
    args = ['--root', str(tmp_path)]
    assert main(args + ['preview', 'op']) == 0
    review = capsys.readouterr().out
    assert fingerprints(tmp_path) == before
    path = tmp_path / 'review.json'; path.write_text(review)
    command = args + ['retry','--review',str(path),'--resolution-id','decision','--actor','human',
                      '--reason','reviewed','--timestamp',STAMP]
    assert main(command) == 0
    assert json.loads(capsys.readouterr().out)['status'] == 'COMMITTED'
    assert main(args + ['preview', 'op']) == 1
    assert json.loads(capsys.readouterr().out)['status'] == 'BLOCKED'


@pytest.mark.parametrize('phase', ['after_authorization', 'after_commit'])
def test_real_process_exit_keeps_authorization_and_resumes(tmp_path, monkeypatch, phase):
    engine = seed(tmp_path, monkeypatch)
    review = review_failed_status(tmp_path, 'op')
    script = '''
import os, sys, json
import core.operations.failed_resolution as m
m._checkpoint = lambda stage: os._exit(74) if stage == sys.argv[3] else None
m.retry_failed_status(sys.argv[1], json.loads(sys.argv[2]), resolution_id='decision', actor='human',
                      reason='reviewed matching snapshots', timestamp='2026-10-02T14:30:00Z')
'''
    result = subprocess.run([sys.executable,'-B','-c',script,str(tmp_path),json.dumps(review),phase])
    assert result.returncode == 74
    assert len(engine.operations.get('op').manual_resolutions) == 1
    assert recover_all(tmp_path)['readiness']['ready']
    assert retry(tmp_path, review)['revision'] == 2


def test_concurrent_same_decision_is_recorded_once(tmp_path, monkeypatch):
    from core.persistence import exclusive_write
    engine = seed(tmp_path, monkeypatch)
    review = review_failed_status(tmp_path, 'op')
    script = '''
import sys, json
from core.operations.failed_resolution import retry_failed_status
print('ready', flush=True)
print(json.dumps(retry_failed_status(sys.argv[1], json.loads(sys.argv[2]), resolution_id='decision',
    actor='human', reason='reviewed matching snapshots', timestamp='2026-10-02T14:30:00Z')))
'''
    with exclusive_write(engine.storage.persistent_root):
        processes = [subprocess.Popen([sys.executable,'-B','-c',script,str(tmp_path),json.dumps(review)],
                                     stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True) for _ in range(2)]
        for process in processes:
            assert process.stdout.readline().strip() == 'ready'
    for process in processes:
        stdout, stderr = process.communicate(timeout=20)
        assert process.returncode == 0, stderr
        assert json.loads(stdout)['status'] == 'COMMITTED'
    assert len(engine.operations.get('op').manual_resolutions) == 1
    assert engine.storage.get('project').revision == 2


def test_a_second_failure_needs_a_new_decision_and_preserves_the_first(tmp_path, monkeypatch):
    import core.operations.failed_resolution as module
    engine = seed(tmp_path, monkeypatch)
    first_review = review_failed_status(tmp_path, 'op')
    def stop(stage):
        if stage == 'after_authorization':
            raise RuntimeError('stopped')
    with monkeypatch.context() as patch:
        patch.setattr(module, '_checkpoint', stop)
        with pytest.raises(RuntimeError):
            retry(tmp_path, first_review)
    applying = engine.operations.get('op')
    first_entry = applying.manual_resolutions[0]
    engine.operations.update(replace(applying, status=OperationStatus.FAILED))
    with pytest.raises(OperationConflict, match='failed again'):
        retry(tmp_path, first_review)
    second_review = review_failed_status(tmp_path, 'op')
    assert second_review['previous_resolutions'] == [first_entry]
    assert second_review['failed_record_sha256'] != first_review['failed_record_sha256']
    retry(tmp_path, second_review, resolution_id='second-decision', reason='second explicit review')
    completed = engine.operations.get('op')
    assert len(completed.manual_resolutions) == 2
    assert completed.manual_resolutions[0] == first_entry
    assert completed.manual_resolutions[1]['reason'] == 'second explicit review'


@pytest.mark.parametrize('field,value', [('actor', 1), ('timestamp','invalid'),
                                         ('review_sha256','bad'), ('action','IGNORE_FAILURE')])
def test_invalid_resolution_metadata_blocks_readiness_and_recovery(tmp_path, monkeypatch, field, value):
    engine = seed(tmp_path, monkeypatch)
    retry(tmp_path, review_failed_status(tmp_path, 'op'))
    path = engine.operations._path('op')
    data = json.loads(path.read_text()); data['manual_resolutions'][0][field] = value
    path.write_text(json.dumps(data))
    before = fingerprints(tmp_path)
    assert not check_readiness(tmp_path)['ready']
    assert not recover_all(tmp_path)['readiness']['ready']
    assert fingerprints(tmp_path) == before


def test_second_failed_status_on_same_target_prevents_ambiguous_retry(tmp_path, monkeypatch):
    engine = seed(tmp_path, monkeypatch)
    original = engine.operations.get('op')
    other = replace(original, operation_id='other', plan=replace(original.plan, event_id='other-event'))
    other = replace(other, execution_plan_hash=plan_hash(other))
    engine.operations.create(other)
    before = fingerprints(tmp_path)
    with pytest.raises(OperationConflict, match='another operation'):
        review_failed_status(tmp_path, 'op')
    assert fingerprints(tmp_path) == before


@pytest.mark.parametrize('field,value', [('format_version', True), ('write_event', 1)])
def test_review_types_cannot_be_changed_through_boolean_numeric_equality(tmp_path, monkeypatch, field, value):
    seed(tmp_path, monkeypatch)
    review = review_failed_status(tmp_path, 'op'); review[field] = value
    before = business_files(tmp_path)
    with pytest.raises((ValueError, OperationConflict)):
        retry(tmp_path, review)
    assert business_files(tmp_path) == before


def test_unchanged_journals_keep_old_shape_and_plan_hash(tmp_path, monkeypatch):
    engine = seed(tmp_path, monkeypatch)
    data = json.loads(engine.operations._path('op').read_text())
    assert 'manual_resolutions' not in data
    expected = data['execution_plan_hash']
    retry(tmp_path, review_failed_status(tmp_path, 'op'))
    assert engine.operations.get('op').execution_plan_hash == expected


def test_symlinked_tree_is_blocked_without_touching_sources(tmp_path, monkeypatch):
    real = tmp_path / 'real'; real.mkdir()
    seed(real, monkeypatch)
    alias = tmp_path / 'alias'; alias.symlink_to(real, target_is_directory=True)
    before = fingerprints(real)
    with pytest.raises(OperationConflict, match='unsafe'):
        review_failed_status(alias, 'op')
    assert fingerprints(real) == before


def test_independent_failed_change_cannot_share_the_reserved_event(tmp_path, monkeypatch):
    engine = seed(tmp_path, monkeypatch)
    seed(tmp_path, monkeypatch, identity='second', opid='second')
    other = engine.operations.get('second')
    other = replace(other, plan=replace(other.plan, event_id='event-op'))
    other = replace(other, execution_plan_hash=plan_hash(other))
    engine.operations._write(other, engine.operations._path('second'))
    before = fingerprints(tmp_path)
    with pytest.raises(OperationConflict, match='Event identity'):
        review_failed_status(tmp_path, 'op')
    assert fingerprints(tmp_path) == before
