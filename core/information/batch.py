# ==========================================================
# Projet      : Eidolon Memory Engine
# Organisation: Eidolon Core Technologies (ECT)
# Fichier     : core/information/batch.py
# Description : Bounded Information writes with one strict reservation scan per locked lot.
# Standard    : Eidolon Presentation Standard v1
# ==========================================================

"""Bounded Information writes with one strict reservation scan per locked lot.

Only the existing per-command journals are durable. The caller retains its
command list; a batch is not an atomic transaction or a persisted input queue.
"""
from contextlib import contextmanager, ExitStack
from dataclasses import replace

from core.backend.errors import BackendError
from core.backend.models import Memory
from core.events.errors import EventRepositoryError
from core.information.write_journal import JournalReservations
from core.operations.errors import OperationConflict, OperationNotFound, OperationRepositoryError
from core.operations.models import OperationType
from core.persistence import exclusive_write
from core.storage_format import decode_json_value

MAX_BATCH_SIZE = 100
ERRORS = (OSError, ValueError, TypeError, KeyError, BackendError,
          EventRepositoryError, OperationRepositoryError)


class _Reservations:
    """Mutable ledger owned by one synchronous lot, never by a writer instance."""
    def __init__(self, snapshot):
        self.pending_by_target = {target: set(ids) for target, ids in snapshot.pending_by_target.items()}
        self.event_ids = set(snapshot.event_ids)

    def require_available(self, target_id, excluding=None):
        JournalReservations.require_available(self, target_id, excluding)

    def committed(self, operation_id, result):
        pending = self.pending_by_target.get(result['information_id'])
        if pending is not None:
            pending.discard(operation_id)
            if not pending:
                del self.pending_by_target[result['information_id']]
        self.event_ids.add(result['event_id'])


class _LockedWrites:
    def __init__(self, backend, stack, writer):
        self.backend, self.stack, self.writer = backend, stack, writer
        self.reservations = None
        self.count = 0
        self.active = True

    def _begin(self):
        if not self.active or self.count >= MAX_BATCH_SIZE:
            raise OperationConflict('closed or exhausted Information batch')
        self.count += 1
        # Lazy initialization preserves no-write lifecycle outcomes: a batch
        # consisting only of STALE/SKIPPED deadlines creates no child journal.
        if self.reservations is None:
            from core.information.writes import FilesystemInformationWrites
            self.writer = self.writer or FilesystemInformationWrites(self.backend)
            self.stack.enter_context(exclusive_write(self.writer.operations.root))
            self.stack.enter_context(exclusive_write(self.writer.events.events_root))
            self.reservations = _Reservations(self.writer._reservations())

    def _execute(self, kind, memory, previous, operation_id, event_id, actor, timestamp):
        try:
            self._begin()
            if ((kind is OperationType.INFORMATION_CREATE and memory.revision != 1)
                    or (kind is OperationType.INFORMATION_UPDATE and
                        (previous < 1 or memory.revision != previous))):
                raise OperationConflict('Memory revision does not match batch command')
            result = self.writer._execute(kind, memory, previous, operation_id, event_id, actor, timestamp,
                                          reservations=self.reservations)
            self.reservations.committed(operation_id, result)
            return result
        except BaseException:
            self.active = False  # Never continue with a ledger after a partial effect.
            raise

    def create(self, memory, *, operation_id, event_id, actor, timestamp):
        return self._execute(OperationType.INFORMATION_CREATE, memory, 0, operation_id, event_id, actor, timestamp)

    def update(self, memory, *, previous_revision, operation_id, event_id, actor, timestamp):
        return self._execute(OperationType.INFORMATION_UPDATE, memory, previous_revision,
                             operation_id, event_id, actor, timestamp)

    def resume(self, operation_id):
        try:
            self._begin()
            entry = self.writer.journal.read(operation_id)
            if entry is None:
                raise OperationNotFound(operation_id)
            result = (self.writer.resume(operation_id) if entry.receipt is not None else
                      self.writer._resume(entry.operation, self.reservations))
            self.reservations.committed(operation_id, result)
            return result
        except BaseException:
            self.active = False
            raise


@contextmanager
def _locked_writes(backend, writer=None):
    """Internal synchronous scope: only this handle writes Information journals.

    No arbitrary writer callback, compaction or unrelated write belongs in this
    scope. Other cooperating processes wait on Persistent/Operation/Event locks.
    """
    with ExitStack() as stack:
        stack.enter_context(exclusive_write(backend.persistent_root))
        batch = _LockedWrites(backend, stack, writer)
        try:
            yield batch
        finally:
            batch.active = False
            batch.reservations = None


def _prepare(writer, commands):
    from core.information.writes import canonical_json
    if not isinstance(commands, list) or not 1 <= len(commands) <= MAX_BATCH_SIZE:
        raise ValueError(f'batch requires 1 to {MAX_BATCH_SIZE} commands')
    # Freeze JSON inputs, including nested Memory extensions, before publication.
    commands = decode_json_value(canonical_json(commands))
    prepared = []
    fields = {'kind', 'memory', 'operation_id', 'event_id', 'actor', 'timestamp'}
    for command in commands:
        if not isinstance(command, dict) or command.get('kind') not in {'CREATE', 'UPDATE'}:
            raise ValueError('batch supports CREATE and UPDATE commands only')
        update = command['kind'] == 'UPDATE'
        if set(command) != fields | ({'previous_revision'} if update else set()):
            raise ValueError('invalid batch command fields')
        memory = Memory(**command['memory'])
        previous = command['previous_revision'] if update else 0
        if (type(previous) is not int or (update and previous < 1)
                or memory.revision != (previous if update else 1)):
            raise OperationConflict('batch Memory revision differs from expected revision')
        writer.backend._serialize_checked(replace(memory, revision=previous + 1))
        writer.backend._path(memory.information_id)
        writer.operations._path(command['operation_id'])
        writer.events._path(command['event_id'])
        if any(not isinstance(command[key], str) or not command[key].strip() for key in ('actor', 'timestamp')):
            raise ValueError('batch actor and stable timestamp required')
        prepared.append((command, memory))
    return prepared


def execute_batch(writer, commands):
    """Stop on first blocked command; earlier commits remain durable/replayable."""
    prepared = _prepare(writer, commands)
    results = []
    with _locked_writes(writer.backend, writer) as batch:
        for index, (command, memory) in enumerate(prepared):
            identity = {key: command[key] for key in ('operation_id', 'event_id', 'actor', 'timestamp')}
            try:
                result = (batch.update(memory, previous_revision=command['previous_revision'], **identity)
                          if command['kind'] == 'UPDATE' else batch.create(memory, **identity))
            except ERRORS as exc:
                return dict(status='BLOCKED', results=results, next_index=index, total=len(prepared),
                            error=dict(operation_id=command['operation_id'], type=type(exc).__name__, reason=str(exc)))
            results.append(dict(index=index, operation_id=command['operation_id'], result=result))
    return dict(status='COMPLETED', results=results, next_index=len(prepared), total=len(prepared), error=None)
