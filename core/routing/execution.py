"""Explicit, resumable STORE/UPDATE → chosen project → canonical dossier.

Version 2 explicitly includes availability and durable schedule registration.
Version 3 adds a deliberately supplied new project template using Thread creation.
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
from core.threads.models import ThreadStatus


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

    def assess(self, memory, context):
        """Handle NONE/REVIEW and explain the next explicit step without writes."""
        from core.routing.outcomes import assess
        return assess(memory, context)

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

    def _validate_policy(self, memory, context, policy, *, include_lifecycle=False, link_only=False):
        if decode_json_value(canonical(asdict(plan(memory, context)))) != policy:
            raise OperationConflict('policy changed or plan does not match its inputs')
        subject = policy['dossier_subject']
        if (policy['persistence'] not in ({'NONE'} if link_only else {'STORE', 'UPDATE'})
                or policy['dossier'] not in {'LINK', 'CREATE_OR_LINK'}
                or not isinstance(subject, dict) or subject.get('kind') != 'project'
                or (policy['proposed_trigger'] is not None and not include_lifecycle) or context.removal_observed
                or (policy['dossier_id'] is not None and policy['dossier_id'] != subject['id'])):
            raise OperationConflict('plan needs review or an unsupported execution capability')
        if link_only and (context.already_stored is not True
                          or context.existing_dossier != subject['id']
                          or policy['applicability'] == 'UNRESOLVED'):
            raise OperationConflict('link-only requires an explicitly chosen existing project and stored source')
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

    def preview_link(self, memory, context, *, project_revision):
        """Version 4: NONE links an exact stored source to a chosen project."""
        self.backend._serialize_checked(memory)
        policy = decode_json_value(canonical(asdict(plan(memory, context))))
        project_id = self._validate_policy(memory, context, policy, link_only=True)
        project = self.storage.get(project_id)
        if project is None or type(project_revision) is not int or project.revision != project_revision:
            raise OperationConflict('existing project with expected revision required')
        current = self.backend.get(memory.information_id)
        if current is None or current != memory:
            raise OperationConflict('link-only needs the exact canonical Information')
        prepared = decode_json_value(canonical({
            'format_version': 4, 'memory': asdict(memory), 'context': asdict(context), 'policy': policy,
            'project_before': self._project_text(project), 'information_before': self._information_text(current)}))
        self._initial_checks(prepared, memory, project)
        return prepared

    def preview_new_project(self, memory, context, *, project):
        """Version 3: explicit new project identity/template, with lifecycle."""
        policy = decode_json_value(canonical(asdict(plan(memory, context))))
        project_id = self._validate_policy(memory, context, policy, include_lifecycle=True)
        if context.existing_dossier is not None or policy['dossier'] != 'CREATE_OR_LINK':
            raise OperationConflict('new project requires explicit CREATE_OR_LINK policy')
        if project.thread_id != project_id or self.storage.get(project_id) is not None:
            raise OperationConflict('new project identity must match an absent project')
        current = self.backend.get(memory.information_id)
        prepared = decode_json_value(canonical({
            'format_version': 3, 'memory': asdict(memory), 'context': asdict(context), 'policy': policy,
            'project_before': None, 'project_create': self._project_text(project),
            'information_before': self._information_text(current)}))
        memory, project = self._inputs(prepared)
        self._initial_checks(prepared, memory, project)
        return prepared

    def _inputs(self, prepared):
        fields = {'format_version', 'memory', 'context', 'policy', 'project_before', 'information_before'}
        if isinstance(prepared, dict) and prepared.get('format_version') == 3:
            fields.add('project_create')
        if (not isinstance(prepared, dict) or set(prepared) != fields
                or type(prepared['format_version']) is not int or prepared['format_version'] not in {1, 2, 3, 4}):
            raise OperationConflict('unknown execution plan format')
        memory = Memory(**prepared['memory'])
        self.backend._serialize_checked(memory)
        project_id = self._validate_policy(memory, restore_context(prepared['context']), prepared['policy'],
                                          include_lifecycle=prepared['format_version'] in {2, 3},
                                          link_only=prepared['format_version'] == 4)
        project = self.storage._deserialize(prepared['project_create'] if prepared['format_version'] == 3
                                            else prepared['project_before'])
        if project.thread_id != project_id:
            raise OperationConflict('project snapshot identity mismatch')
        if prepared['format_version'] == 3:
            from core.threads.manager import ThreadManager
            from core.lifecycle.journal import timestamp
            ThreadManager.validate(project)
            timestamp(project.created_at)
            if (prepared['project_before'] is not None or project.revision != 1
                    or project.status is not ThreadStatus.PROPOSED or project.actions or project.relations
                    or project.updated_at != project.created_at
                    or project.started_at is not None or project.completed_at is not None
                    or prepared['context'].get('existing_dossier') is not None
                    or prepared['policy']['dossier'] != 'CREATE_OR_LINK'):
                raise OperationConflict('new project must be a fresh explicit PROPOSED template')
        if prepared['format_version'] == 4 and prepared['information_before'] != self._information_text(memory):
            raise OperationConflict('link-only snapshot differs from the supplied canonical Information')
        return memory, project

    @staticmethod
    def _lifecycle_memory(memory, prepared):
        if prepared['format_version'] in {1, 4}:
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
        if prepared['format_version'] != 3 and memory.information_id not in self.storage._concerns(project):
            apply_command(project, {'kind': 'LINK', 'information_id': memory.information_id}, project.updated_at)

    def execute(self, prepared, *, intent_id, actor, timestamp):
        self.journal.path(intent_id)
        if not isinstance(actor, str) or not actor or not isinstance(timestamp, str) or not timestamp:
            raise ValueError('actor and timestamp required')
        command = decode_json_value(canonical({'prepared': prepared, 'actor': actor, 'timestamp': timestamp}))
        fingerprint = digest(command)
        if isinstance(prepared, dict) and prepared.get('format_version') == 3:
            ThreadStorage(self.backend.persistent_root)
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
            if prepared['format_version'] >= 2:
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
            with exclusive_write(writes.operations.root):
                writes._pending(memory.information_id)
                if prepared['format_version'] == 4 and writes.journal.read(self.child_id(intent_id, 'information')) is not None:
                    raise OperationConflict('link-only intent has a conflicting Information child')
            threads = ThreadService.for_backend(self.backend)
            threads.updates._other_pending(project.thread_id, self.child_id(intent_id, 'project'))
            if prepared['format_version'] == 3:
                # A deleted identity is not a new project. Never start the
                # Information child when a prior creation/deletion owns it.
                for repository in (threads.creation.operations, threads.deletion.operations):
                    for path in repository.root.glob('*.json'):
                        prior = repository.get(path.stem)
                        if prior is not None and prior.target_id == project.thread_id:
                            raise OperationConflict('project identity has prior creation/deletion history')
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
            if prepared['format_version'] == 4 and child is not None:
                raise OperationConflict('link-only intent cannot own an Information write child')
            permitted = {prepared['information_before']}
            if child is not None:
                permitted.add(expected_info)
            if self._information_text(self.backend.get(memory.information_id)) not in permitted:
                raise OperationConflict('Information diverged during routing execution')
            link = {'kind': 'LINK', 'information_id': memory.information_id}
            creating = prepared['format_version'] == 3
            already_linked = not creating and memory.information_id in self.storage._concerns(before_project)
            after_project = (threads.creation.links.prepare(before_project, memory.information_id) if creating else
                             before_project if already_linked else apply_command(before_project, link, command['timestamp']))
            child_project = (threads.creation.operations if creating else threads.updates.operations).get(project_id)
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
            elif prepared['policy']['persistence'] == 'UPDATE':
                writes.update(memory, previous_revision=memory.revision, **identity)
            self._checkpoint('after_information')
            if creating:
                threads.create_linked(before_project, memory.information_id,
                                      operation_id=project_id, event_id=project_id + '-event')
            elif not already_linked:
                threads.update_thread(before_project.thread_id, link, previous_revision=before_project.revision,
                                      operation_id=project_id, event_id=project_id + '-event',
                                      actor=command['actor'], timestamp=command['timestamp'])
            self._checkpoint('after_project')
            projection = self.dossiers.rebuild(before_project.thread_id)
            self._checkpoint('after_projection')
            result = {'information': {'id': memory.information_id, 'revision': after_memory.revision},
                      'project': {'id': before_project.thread_id, 'revision': after_project.revision},
                      'projection_digest': projection['source_digest'], 'deferred': ['availability']}
            if prepared['format_version'] in {2, 3}:
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
