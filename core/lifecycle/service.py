"""Availability changes and durable deadlines, driven by an explicit caller clock."""
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import replace
from hashlib import sha256

from core.backend.errors import BackendError
from core.events.errors import EventRepositoryError
from core.information.writes import FilesystemInformationWrites, fingerprint
from core.information.write_journal import InformationWriteJournal
from core.lifecycle.journal import TriggerJournal, identity, timestamp
from core.operations.errors import OperationConflict, OperationRepositoryError
from core.operations.models import OperationType
from core.persistence import exclusive_write
from core.routing.execution_journal import digest, owned_execution, require_available
from core.routing.policy import applicability


class AvailabilityService:
    def __init__(self, backend):
        self.backend = backend

    def set_level(self, memory, level, **command):
        """Caller supplies the original Memory snapshot for stable journal replay."""
        if level not in {'HIGH', 'INTERMEDIATE', 'LOW'}:
            raise ValueError('unknown availability level')
        changed = replace(memory, metadata=dict(deepcopy(memory.metadata), availability=level))
        return FilesystemInformationWrites(self.backend).update(changed, previous_revision=memory.revision, **command)

    def acknowledge_review(self, memory, **command):
        """Explicit review acknowledgement; never changes truth, validity or content."""
        changed = replace(memory, metadata=dict(deepcopy(memory.metadata), recheck_required=False))
        return FilesystemInformationWrites(self.backend).update(changed, previous_revision=memory.revision, **command)


class LifecycleTriggers:
    def __init__(self, backend):
        if (backend.persistent_root.name != 'persistent' or backend.persistent_root.parent.name != 'memory'
                or backend.history_root.absolute() != (backend.persistent_root.parent / 'history').absolute()):
            raise ValueError('lifecycle requires canonical engine roots')
        self.backend = backend
        self.root = backend.persistent_root.parent.parent
        self.journal = TriggerJournal(backend.history_root)

    @staticmethod
    def _checkpoint(stage):
        """Durable boundaries for process interruption tests."""

    @staticmethod
    def child_ids(trigger_id):
        base = 'lifecycle-' + sha256(trigger_id.encode()).hexdigest()
        return base + '-write', base + '-event'

    @contextmanager
    def _locked(self):
        self.journal.ids()  # Validate paths before mkdir.
        with exclusive_write(self.backend.persistent_root):
            self.journal.root.mkdir(parents=True, exist_ok=True)
            with exclusive_write(self.journal.root):
                yield

    def schedule(self, target_id, *, revision, kind, due_at, trigger_id, actor, created_at):
        identity(target_id)
        identity(trigger_id)
        timestamp(due_at)
        timestamp(created_at)
        command = dict(target_id=target_id, revision=revision, kind=kind,
                       due_at=due_at, actor=actor, created_at=created_at)
        candidate = dict(format_version=1, trigger_id=trigger_id, status='SCHEDULED',
                         command=command, fingerprint=digest(command), source_sha256='0' * 64,
                         run=None, result=None)
        self.journal.validate(candidate, trigger_id)
        with self._locked():
            prior = self.journal.read(trigger_id)
            if prior is not None:
                if prior['fingerprint'] != candidate['fingerprint']:
                    raise OperationConflict('trigger_id reused with different command')
                return prior
            from core.operations.readiness import check_readiness
            owner = owned_execution(self.backend.history_root)
            owned_path = 'memory/history/operations/routing-execution-v1/' + owner + '.json' if owner else None
            issues = check_readiness(self.root)['issues']
            if any(not (issue['path'] == owned_path and issue['reason'] == 'APPLYING' and issue['resumable'])
                   for issue in issues):
                raise OperationConflict('recover or review before scheduling')
            memory = self.backend.get(target_id)
            if memory is None or memory.revision != revision:
                raise OperationConflict('schedule requires existing expected revision')
            if self._deletion(target_id) not in {None, 'CANCELLED'}:
                raise OperationConflict('cannot schedule a deletion-pending source')
            candidate['source_sha256'] = sha256(self.backend._path(target_id).read_bytes()).hexdigest()
            self.journal.save(candidate)
            return candidate

    def _deletion(self, target_id):
        path = self.backend.pending_delete_root / (target_id + '.json')
        return self.backend._load_delete_request(path, target_id)['status'] if path.exists() or path.is_symlink() else None

    def _finish(self, record, status, reason, at, actor, information=None):
        record = dict(record, status=status,
                      result=dict(reason=reason, at=at, actor=actor, information=information))
        self.journal.save(record)
        return record

    def cancel(self, trigger_id, *, actor, at, reason):
        timestamp(at)
        if any(not isinstance(value, str) or not value.strip() for value in (actor, reason)):
            raise ValueError('cancellation actor and reason required')
        with self._locked():
            record = self.journal.read(trigger_id)
            if record is None:
                raise OperationConflict('unknown lifecycle trigger')
            if record['status'] == 'CANCELLED':
                if record['result'] != dict(reason=reason, at=at, actor=actor, information=None):
                    raise OperationConflict('cancellation changed after acknowledgement')
                return record
            if record['status'] != 'SCHEDULED':
                raise OperationConflict('only a scheduled trigger can be cancelled')
            return self._finish(record, 'CANCELLED', reason, at, actor)

    @staticmethod
    def _changed(memory, effect):
        metadata = deepcopy(memory.metadata)
        metadata['availability'] = 'HIGH' if effect == 'HIGH' else 'INTERMEDIATE'
        if effect == 'RECHECK':
            metadata['recheck_required'] = True
        return replace(memory, metadata=metadata)

    def _run(self, record, *, at=None, query_scope=None):
        command = record['command']
        target = command['target_id']
        opid, event_id = self.child_ids(record['trigger_id'])
        # The child journal is authoritative if an effect began or committed
        # before the parent acknowledgement. Never infer success from revision.
        child = InformationWriteJournal(self.backend.history_root).read(opid)
        if record['status'] == 'APPLYING' and child is not None:
            if child.fingerprint != record['run']['fingerprint']:
                raise OperationConflict('lifecycle child command diverged')
            result = FilesystemInformationWrites(self.backend).resume(opid)
            self._checkpoint('after_effect')
            return self._finish(record, 'COMPLETED', record['run']['effect'],
                                record['run']['at'], command['actor'], result)
        if child is not None:
            raise OperationConflict('unexpected lifecycle child operation')
        # A registered deadline must not begin its effect while its parent
        # route still owns the source, including after a process interruption.
        require_available(self.backend.history_root, information_id=target)
        memory = self.backend.get(target)
        at = record['run']['at'] if record['run'] is not None else at
        if (memory is None or memory.revision != command['revision']
                or sha256(self.backend._path(target).read_bytes()).hexdigest() != record['source_sha256']):
            return self._finish(record, 'STALE', 'source_changed_or_removed', at, command['actor'])
        if self._deletion(target) not in {None, 'CANCELLED'}:
            return self._finish(record, 'SKIPPED', 'source_pending_deletion', at, command['actor'])
        if record['run'] is None:
            epistemic = memory.metadata.get('epistemic_status')
            try:
                applies = applicability(memory, query_scope, at=at, unresolved_conflict=epistemic == 'CONFLICTED')
            except (AttributeError, TypeError, ValueError):
                applies = 'UNKNOWN'
            if command['kind'] == 'REACTIVATE' and (applies in {'EXPIRED', 'OUT_OF_SCOPE'} or epistemic in {'REFUTED', 'SUPERSEDED'}):
                return self._finish(record, 'SKIPPED', 'reactivation_inapplicable', at, command['actor'])
            qualification = memory.metadata.get('qualification')
            nature = qualification.get('nature') if isinstance(qualification, dict) else None
            effect = ('HIGH' if command['kind'] == 'REACTIVATE' and applies == 'MATCH'
                      and epistemic == 'CONFIRMED' and nature not in {'MOBILE_PRESENCE', 'OBSTACLE'}
                      and not memory.metadata.get('recheck_required') else 'RECHECK')
            after = self._changed(memory, effect)
            child_fingerprint = fingerprint(OperationType.INFORMATION_UPDATE, replace(after, revision=memory.revision + 1),
                                            memory.revision, event_id, command['actor'], at)
            record = dict(record, status='APPLYING', run=dict(at=at, query_scope=deepcopy(query_scope),
                          effect=effect, fingerprint=child_fingerprint))
            self.journal.save(record)
            self._checkpoint('after_intent')
        after = self._changed(memory, record['run']['effect'])
        expected = fingerprint(OperationType.INFORMATION_UPDATE, replace(after, revision=memory.revision + 1),
                               memory.revision, event_id, command['actor'], record['run']['at'])
        if expected != record['run']['fingerprint']:
            raise OperationConflict('lifecycle execution fingerprint changed')
        result = FilesystemInformationWrites(self.backend).update(
            after, previous_revision=memory.revision, operation_id=opid, event_id=event_id,
            actor=command['actor'], timestamp=record['run']['at'])
        self._checkpoint('after_effect')
        return self._finish(record, 'COMPLETED', record['run']['effect'], record['run']['at'], command['actor'], result)

    def run_due(self, *, at, query_scope=None, limit=100):
        instant = timestamp(at)
        if type(limit) is not int or limit < 1 or (query_scope is not None and not isinstance(query_scope, dict)):
            raise ValueError('positive limit and object query_scope required')
        scope = deepcopy(query_scope) if query_scope is not None else {}
        with self._locked():
            from core.operations.readiness import check_readiness
            readiness = check_readiness(self.root)
            if any(not issue['resumable'] for issue in readiness['issues']):
                raise OperationConflict('unresolved corruption or FAILED blocks lifecycle dispatch')
            records = [self.journal.read(i) for i in self.journal.ids()]
            eligible = [r for r in records if r['status'] == 'APPLYING' or
                        (r['status'] == 'SCHEDULED' and timestamp(r['command']['due_at']) <= instant)]
            eligible.sort(key=lambda r: (timestamp(r['command']['due_at']), r['trigger_id']))
            return {r['trigger_id']: self._run(r, at=at, query_scope=scope) for r in eligible[:limit]}

    def recover(self):
        results = {}
        for trigger_id in self.journal.ids():
            try:
                with self._locked():
                    record = self.journal.read(trigger_id)
                    if record['status'] == 'APPLYING':
                        results[trigger_id] = self._run(record)
            except (OSError, ValueError, TypeError, BackendError, OperationRepositoryError, EventRepositoryError) as exc:
                results[trigger_id] = {'status': 'BLOCKED', 'error': type(exc).__name__}
        return results
