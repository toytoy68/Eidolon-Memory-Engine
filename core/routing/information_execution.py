# ==========================================================
# Projet      : Eidolon Memory Engine
# Organisation: Eidolon Core Technologies (ECT)
# Fichier     : core/routing/information_execution.py
# Description : Explicit qualified Information-only routing, without project creation.
# Standard    : Eidolon Presentation Standard v1
# ==========================================================

"""Explicit qualified Information-only routing, without project creation."""
from contextlib import contextmanager, ExitStack
from dataclasses import asdict, replace

from core.backend.models import Memory
from core.information.writes import FilesystemInformationWrites
from core.operations.errors import OperationConflict
from core.operations.models import OperationType
from core.operations.readiness import check_readiness
from core.persistence import exclusive_write
from core.routing.execution_journal import canonical, digest, execution_owner, require_available
from core.routing.policy import plan
from core.storage_format import decode_json_value


@contextmanager
def locks(executor):
    # Existing project writers share this order; an Information-only tree does
    # not need a synthetic Thread directory just to acquire a lock.
    with ExitStack() as stack:
        stack.enter_context(exclusive_write(executor.backend.persistent_root))
        if executor.storage.threads_root.is_dir():
            stack.enter_context(exclusive_write(executor.storage.threads_root))
        stack.enter_context(exclusive_write(executor.journal.root))
        yield


def inputs(executor, prepared):
    from core.routing.execution import restore_context
    fields = {'format_version', 'memory', 'context', 'policy', 'project_before', 'information_before'}
    if (not isinstance(prepared, dict) or set(prepared) != fields
            or type(prepared['format_version']) is not int or prepared['format_version'] != 5
            or prepared['project_before'] is not None):
        raise OperationConflict('invalid Information-only plan')
    memory = Memory(**prepared['memory'])
    executor.backend._serialize_checked(memory)
    context = restore_context(prepared['context'])
    policy = prepared['policy']
    if (policy != decode_json_value(canonical(asdict(plan(memory, context))))
            or policy['persistence'] not in {'STORE', 'UPDATE'} or policy['dossier'] != 'NONE'
            or policy['dossier_subject'] is not None or context.existing_dossier is not None
            or context.removal_observed or policy['applicability'] == 'UNRESOLVED'):
        raise OperationConflict('plan requires review or an explicit dossier capability')
    if policy['persistence'] == 'STORE':
        if memory.revision != 1 or prepared['information_before'] is not None:
            raise OperationConflict('STORE requires an absent revision-one source')
    else:
        target = context.update_target
        if (target is None or target.information_id != memory.information_id
                or target.revision != memory.revision or prepared['information_before'] is None):
            raise OperationConflict('UPDATE requires an explicit matching source revision')
        before = executor.backend._deserialize(prepared['information_before'])
        if before.information_id != memory.information_id or before.revision != memory.revision:
            raise OperationConflict('UPDATE snapshot identity/revision mismatch')
    trigger = policy['proposed_trigger']
    if trigger is not None:
        from core.lifecycle.journal import timestamp
        if trigger['kind'] != 'REACTIVATE':
            raise OperationConflict('unsupported lifecycle proposal')
        timestamp(trigger['at'])
    return memory


def initial_checks(executor, prepared, memory):
    require_available(executor.backend.history_root, information_id=memory.information_id)
    if executor._information_text(executor.backend.get(memory.information_id)) != prepared['information_before']:
        raise OperationConflict('Information-only plan is stale')


def preview(executor, memory, context):
    executor.backend._serialize_checked(memory)
    prepared = decode_json_value(canonical({
        'format_version': 5, 'memory': asdict(memory), 'context': asdict(context),
        'policy': asdict(plan(memory, context)), 'project_before': None,
        'information_before': executor._information_text(executor.backend.get(memory.information_id))}))
    inputs(executor, prepared)
    initial_checks(executor, prepared, memory)
    return prepared


def execute(executor, prepared, *, intent_id, actor, timestamp):
    from core.lifecycle.journal import timestamp as validate_timestamp
    executor.journal.path(intent_id)
    if not isinstance(actor, str) or not actor.strip():
        raise ValueError('actor required')
    validate_timestamp(timestamp)
    command = decode_json_value(canonical({'prepared': prepared, 'actor': actor, 'timestamp': timestamp}))
    fingerprint = digest(command)
    executor.journal.root.mkdir(parents=True, exist_ok=True)
    with locks(executor):
        existing = executor.journal.read(intent_id)
        if existing is not None:
            if existing['fingerprint'] != fingerprint:
                raise OperationConflict('intent_id reused with a different plan')
            return existing['result'] if existing['status'] == 'COMMITTED' else resume(executor, existing)
        memory = inputs(executor, command['prepared'])
        if not check_readiness(executor.backend.persistent_root.parent.parent)['ready']:
            raise OperationConflict('recover or review before Information-only routing')
        initial_checks(executor, command['prepared'], memory)
        writes = FilesystemInformationWrites(executor.backend)
        kind = OperationType.INFORMATION_CREATE if prepared['policy']['persistence'] == 'STORE' else OperationType.INFORMATION_UPDATE
        writes._check_deletion(kind, memory.information_id)
        with exclusive_write(writes.operations.root):
            writes._pending(memory.information_id)
            if writes.journal.read(executor.child_id(intent_id, 'information')) is not None:
                raise OperationConflict('Information-only intent has a foreign write child')
        record = dict(format_version=5, intent_id=intent_id, status='APPLYING', fingerprint=fingerprint, command=command)
        executor.journal.save(record)
        return resume(executor, record)


def resume(executor, record):
    command = record['command']; prepared = command['prepared']
    memory = executor._lifecycle_memory(inputs(executor, prepared), prepared)
    intent = record['intent_id']
    with execution_owner(executor.backend.history_root, intent):
        writes = FilesystemInformationWrites(executor.backend)
        child_id = executor.child_id(intent, 'information')
        after = replace(memory, revision=memory.revision + 1) if prepared['policy']['persistence'] == 'UPDATE' else memory
        permitted = {prepared['information_before']}
        if writes.journal.read(child_id) is not None:
            permitted.add(executor._information_text(after))
        if executor._information_text(executor.backend.get(memory.information_id)) not in permitted:
            raise OperationConflict('Information diverged during routing execution')
        executor._checkpoint('before_information')
        identity = dict(operation_id=child_id, event_id=child_id + '-event', actor=command['actor'], timestamp=command['timestamp'])
        if prepared['policy']['persistence'] == 'STORE':
            writes.create(memory, **identity)
        else:
            writes.update(memory, previous_revision=memory.revision, **identity)
        executor._checkpoint('after_information')
        trigger = prepared['policy']['proposed_trigger']
        trigger_id = executor.child_id(intent, 'trigger') if trigger is not None else None
        if trigger is not None:
            from core.lifecycle.service import LifecycleTriggers
            LifecycleTriggers(executor.backend).schedule(memory.information_id, revision=after.revision,
                kind=trigger['kind'], due_at=trigger['at'], trigger_id=trigger_id,
                actor=command['actor'], created_at=command['timestamp'])
        executor._checkpoint('after_trigger')
        result = dict(information={'id': memory.information_id, 'revision': after.revision}, project=None,
                      projection_digest=None, deferred=[],
                      lifecycle={'availability': prepared['policy']['availability'], 'trigger_id': trigger_id})
        receipt = {key: record[key] for key in ('format_version', 'intent_id', 'fingerprint')}
        receipt.update(status='COMMITTED', result=result)
        executor.journal.save(receipt)
        return result
