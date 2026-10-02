"""Explicit, resumable STORE/UPDATE → existing project → canonical dossier.

Version 2 explicitly includes availability and durable schedule registration.
An intent owns its targets until the derived view is rebuilt and a compact result
replaces the command. Child services remain responsible for their own journals.
"""
from dataclasses import asdict, replace
from copy import deepcopy
from hashlib import sha256
from pathlib import Path

from core.backend.errors import BackendError
from core.backend.models import Memory
from core.dossiers.projects import ProjectDossiers, DossierConflict
from core.events.errors import EventRepositoryError
from core.information.writes import FilesystemInformationWrites
from core.operations.errors import OperationConflict, OperationRepositoryError
from core.operations.thread_update import apply_command
from core.persistence import exclusive_write
from core.routing.execution_journal import ExecutionJournal, canonical, digest, execution_owner, require_available
from core.routing.policy import RoutingContext, TargetRevision, plan
from core.storage_format import decode_json_value
from core.threads.service import ThreadService
from core.threads.storage import ThreadStorage, ThreadStorageError
from core.threads.manager import ThreadError


def restore_context(value):
    value = dict(value)
    if value.get('update_target') is not None:
        value['update_target'] = TargetRevision(**value['update_target'])
    for key in ('candidate_projects', 'evidence_refs'):
        if key in value:
            value[key] = tuple(value[key])
    return RoutingContext(**value)


class RoutingExecutor:
    def __init__(self, backend):
        if (backend.persistent_root.name != 'persistent'
                or backend.history_root.absolute() != (backend.persistent_root.parent / 'history').absolute()):
            raise ValueError('routing execution requires canonical persistent/history siblings')
        self.backend = backend
        # Readers do not initialize a journal or Thread directory during preview.
        self.storage = ThreadStorage.__new__(ThreadStorage)
        self.storage.persistent_root = backend.persistent_root
        self.storage.threads_root = backend.persistent_root / 'threads'
        self.journal = ExecutionJournal(backend.history_root)
        self.dossiers = ProjectDossiers(backend, self.storage, backend.persistent_root.parent / 'dossiers')

    def recall(self, query, **options):
        """Read canonical contextual memory; no implicit projection rebuild."""
        from core.retrieval.contextual import ContextualRecall
        return ContextualRecall(self.backend).recall(query, **options)

    @staticmethod
    def child_id(intent, step):
        return 'routing-' + sha256(intent.encode()).hexdigest() + '-' + step

    @staticmethod
    def _checkpoint(stage):
        """Named durable boundaries used by fault-injection tests."""

    def _information_text(self, memory):
        return None if memory is None else self.backend._serialize_checked(memory)

    def _project_text(self, project):
        return None if project is None else self.storage._serialize_checked(project)

    def _validate_policy(self, memory, context, policy, *, include_lifecycle=False):
        if decode_json_value(canonical(asdict(plan(memory, context)))) != policy:
            raise OperationConflict('policy changed or plan does not match its inputs')
        subject = policy['dossier_subject']
        if (policy['persistence'] not in {'STORE', 'UPDATE'}
                or policy['dossier'] not in {'LINK', 'CREATE_OR_LINK'}
                or not isinstance(subject, dict) or subject.get('kind') != 'project'
                or (policy['proposed_trigger'] is not None and not include_lifecycle) or context.removal_observed
                or (policy['dossier_id'] is not None and policy['dossier_id'] != subject['id'])):
            raise OperationConflict('plan needs review or an unsupported execution capability')
        if include_lifecycle and policy['proposed_trigger'] is not None:
            from core.lifecycle.journal import timestamp
            trigger = policy['proposed_trigger']
            if trigger['kind'] != 'REACTIVATE':
                raise OperationConflict('unsupported lifecycle proposal')
            timestamp(trigger['at'])
        self.storage._path(subject['id'])
        target = context.update_target
        if policy['persistence'] == 'STORE' and memory.revision != 1:
            raise OperationConflict('new Information must start at revision 1')
        if policy['persistence'] == 'UPDATE' and (
            target is None or target.information_id != memory.information_id or target.revision != memory.revision
        ):
            raise OperationConflict('update target identity/revision mismatch')
        return subject['id']

    def preview(self, memory, context, *, project_revision, include_lifecycle=False):
        if type(include_lifecycle) is not bool:
            raise ValueError('include_lifecycle must be boolean')
        self.backend._serialize_checked(memory)
        policy = decode_json_value(canonical(asdict(plan(memory, context))))
        project_id = self._validate_policy(memory, context, policy, include_lifecycle=include_lifecycle)
        project = self.storage.get(project_id)
        if project is None or type(project_revision) is not int or project.revision != project_revision:
            raise OperationConflict('existing project with expected revision required')
        current = self.backend.get(memory.information_id)
        if policy['persistence'] == 'STORE' and current is not None:
            raise OperationConflict('Information already exists')
        if policy['persistence'] == 'UPDATE' and (current is None or current.revision != memory.revision):
            raise OperationConflict('Information revision changed')
        # Frozen JSON values, not aliases to caller-owned mutable dictionaries.
        return decode_json_value(canonical({
            'format_version': 2 if include_lifecycle else 1, 'memory': asdict(memory), 'context': asdict(context), 'policy': policy,
            'project_before': self._project_text(project), 'information_before': self._information_text(current)}))

    def _inputs(self, prepared):
        if (not isinstance(prepared, dict) or set(prepared) != {
                'format_version', 'memory', 'context', 'policy', 'project_before', 'information_before'}
                or type(prepared['format_version']) is not int or prepared['format_version'] not in {1, 2}):
            raise OperationConflict('unknown execution plan format')
        memory = Memory(**prepared['memory'])
        self.backend._serialize_checked(memory)
        project_id = self._validate_policy(memory, restore_context(prepared['context']), prepared['policy'],
                                          include_lifecycle=prepared['format_version'] == 2)
        project = self.storage._deserialize(prepared['project_before'])
        if project.thread_id != project_id:
            raise OperationConflict('project snapshot identity mismatch')
        return memory, project

    @staticmethod
    def _lifecycle_memory(memory, prepared):
        if prepared['format_version'] == 1:
            return memory
        metadata = deepcopy(memory.metadata)
        metadata['availability'] = prepared['policy']['availability']
        if prepared['policy']['recheck_before_reuse']:
            metadata['recheck_required'] = True
        return replace(memory, metadata=metadata)

    def _initial_checks(self, prepared, memory, project):
        require_available(self.backend.history_root, information_id=memory.information_id, thread_id=project.thread_id)
        if (self._project_text(self.storage.get(project.thread_id)) != prepared['project_before']
                or self._information_text(self.backend.get(memory.information_id)) != prepared['information_before']):
            raise OperationConflict('execution plan is stale')
        if prepared['policy']['persistence'] == 'STORE' and prepared['information_before'] is not None:
            raise OperationConflict('STORE has an existing source')
        if prepared['policy']['persistence'] == 'UPDATE':
            if prepared['information_before'] is None:
                raise OperationConflict('UPDATE needs an existing source')
            before = self.backend._deserialize(prepared['information_before'])
            if before.information_id != memory.information_id or before.revision != memory.revision:
                raise OperationConflict('UPDATE snapshot identity/revision mismatch')
        # Plan validation cannot reserve a closed project for an impossible link.
        if memory.information_id not in self.storage._concerns(project):
            apply_command(project, {'kind': 'LINK', 'information_id': memory.information_id}, project.updated_at)

    def execute(self, prepared, *, intent_id, actor, timestamp):
        self.journal.path(intent_id)
        if not isinstance(actor, str) or not actor or not isinstance(timestamp, str) or not timestamp:
            raise ValueError('actor and timestamp required')
        command = decode_json_value(canonical({'prepared': prepared, 'actor': actor, 'timestamp': timestamp}))
        fingerprint = digest(command)
        self.journal.root.mkdir(parents=True, exist_ok=True)
        with exclusive_write(self.backend.persistent_root), exclusive_write(self.storage.threads_root), exclusive_write(self.journal.root):
            existing = self.journal.read(intent_id)
            if existing is not None:
                if existing['fingerprint'] != fingerprint:
                    raise OperationConflict('intent_id reused with a different plan')
                if existing['status'] == 'COMMITTED':
                    return existing['result']
                return self._resume(existing)
            memory, project = self._inputs(command['prepared'])
            if prepared['format_version'] == 2:
                from core.lifecycle.journal import timestamp as validate_timestamp
                from core.operations.readiness import check_readiness
                validate_timestamp(timestamp)
                if not check_readiness(self.backend.persistent_root.parent.parent)['ready']:
                    raise OperationConflict('recover or review before lifecycle routing')
            self._initial_checks(command['prepared'], memory, project)
            # Refuse known child conflicts before reserving the overall journey.
            writes = FilesystemInformationWrites(self.backend)
            from core.operations.models import OperationType
            kind = OperationType.INFORMATION_CREATE if command['prepared']['policy']['persistence'] == 'STORE' else OperationType.INFORMATION_UPDATE
            writes._check_deletion(kind, memory.information_id)
            writes._pending(memory.information_id)
            threads = ThreadService.for_backend(self.backend)
            threads.updates._other_pending(project.thread_id, self.child_id(intent_id, 'project'))
            record = {'format_version': prepared['format_version'], 'intent_id': intent_id, 'status': 'APPLYING',
                      'fingerprint': fingerprint, 'command': command}
            self.journal.save(record)
            return self._resume(record)

    def _resume(self, record):
        command = record['command']
        prepared = command['prepared']
        memory, before_project = self._inputs(prepared)
        memory = self._lifecycle_memory(memory, prepared)
        intent = record['intent_id']
        with execution_owner(self.backend.history_root, intent):
            writes = FilesystemInformationWrites(self.backend)
            threads = ThreadService.for_backend(self.backend)
            info_id = self.child_id(intent, 'information')
            project_id = self.child_id(intent, 'project')
            after_memory = replace(memory, revision=memory.revision + 1) if prepared['policy']['persistence'] == 'UPDATE' else memory
            expected_info = self._information_text(after_memory)
            child = writes.journal.read(info_id)
            permitted = {prepared['information_before']}
            if child is not None:
                permitted.add(expected_info)
            if self._information_text(self.backend.get(memory.information_id)) not in permitted:
                raise OperationConflict('Information diverged during routing execution')
            link = {'kind': 'LINK', 'information_id': memory.information_id}
            already_linked = memory.information_id in self.storage._concerns(before_project)
            after_project = before_project if already_linked else apply_command(before_project, link, command['timestamp'])
            child_project = threads.updates.operations.get(project_id)
            allowed_projects = {prepared['project_before']}
            if child_project is not None:
                allowed_projects.add(self._project_text(after_project))
            if self._project_text(self.storage.get(before_project.thread_id)) not in allowed_projects:
                raise OperationConflict('project diverged during routing execution')
            self._checkpoint('before_information')
            identity = {'operation_id': info_id, 'event_id': info_id + '-event',
                        'actor': command['actor'], 'timestamp': command['timestamp']}
            if prepared['policy']['persistence'] == 'STORE':
                writes.create(memory, **identity)
            else:
                writes.update(memory, previous_revision=memory.revision, **identity)
            self._checkpoint('after_information')
            if not already_linked:
                threads.update_thread(before_project.thread_id, link, previous_revision=before_project.revision,
                                      operation_id=project_id, event_id=project_id + '-event',
                                      actor=command['actor'], timestamp=command['timestamp'])
            self._checkpoint('after_project')
            projection = self.dossiers.rebuild(before_project.thread_id)
            self._checkpoint('after_projection')
            result = {'information': {'id': memory.information_id, 'revision': after_memory.revision},
                      'project': {'id': before_project.thread_id, 'revision': after_project.revision},
                      'projection_digest': projection['source_digest'], 'deferred': ['availability']}
            if prepared['format_version'] == 2:
                from core.lifecycle.service import LifecycleTriggers
                trigger = prepared['policy']['proposed_trigger']
                trigger_id = self.child_id(intent, 'trigger') if trigger is not None else None
                if trigger is not None:
                    LifecycleTriggers(self.backend).schedule(
                        memory.information_id, revision=after_memory.revision, kind=trigger['kind'],
                        due_at=trigger['at'], trigger_id=trigger_id,
                        actor=command['actor'], created_at=command['timestamp'])
                self._checkpoint('after_trigger')
                result.update(deferred=[], lifecycle={'availability': prepared['policy']['availability'],
                                                      'trigger_id': trigger_id})
            # Atomic replacement drops the sensitive parent snapshots. Child
            # journals retain their own documented compaction/retention rules.
            receipt = {key: record[key] for key in ('format_version', 'intent_id', 'fingerprint')}
            receipt.update(status='COMMITTED', result=result)
            self.journal.save(receipt)
            return result

    def recover(self):
        results = {}
        for identity in self.journal.ids():
            try:
                with exclusive_write(self.backend.persistent_root), exclusive_write(self.storage.threads_root), exclusive_write(self.journal.root):
                    record = self.journal.read(identity)
                    if record['status'] == 'COMMITTED':
                        continue
                    self._resume(record)
                results[identity] = {'status': 'COMMITTED'}
            except (OSError, ValueError, TypeError, KeyError, BackendError, OperationRepositoryError,
                    EventRepositoryError, ThreadStorageError, ThreadError, DossierConflict) as exc:
                results[identity] = {'status': 'BLOCKED', 'error': type(exc).__name__}
        return results
