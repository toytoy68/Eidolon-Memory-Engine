"""Application service for Eidolon Threads."""

from __future__ import annotations

from .manager import ThreadManager
from .models import Thread
from .queries import ThreadQuery, ThreadQueryType
from .request_mapping import build_thread_query
from .requests import ThreadRequest
from .storage import ThreadStorage


class ThreadService:
    """Coordinate Thread persistence and domain queries."""

    def __init__(self, storage: ThreadStorage, operations=None, creation=None,
                 deletion=None, updates=None) -> None:
        self.storage = storage
        self.operations = operations
        self.creation = creation
        self.deletion = deletion
        self.updates = updates

    @classmethod
    def for_backend(cls, backend):
        """Canonical construction; callers no longer choose individual journals."""
        from core.events.filesystem import FilesystemEventRepository
        from core.operations.filesystem import FilesystemOperationRepository
        from core.operations.thread_create import FilesystemLinkedThreadCreation
        from core.operations.thread_delete import FilesystemThreadDeletion
        from core.operations.thread_status import FilesystemThreadOperations
        from core.operations.thread_update import FilesystemThreadUpdates
        storage = ThreadStorage(backend.persistent_root)
        history = backend.history_root
        journals = {family: FilesystemOperationRepository(history / 'operations' / family)
                    for family in ('thread-create-v1', 'thread-status-v1', 'thread-delete-v1')}
        creation = FilesystemLinkedThreadCreation(
            backend, storage, FilesystemEventRepository(history / 'events/thread-create-v1'),
            journals['thread-create-v1'], deletion_operations=journals['thread-delete-v1'])
        changes = FilesystemThreadOperations(
            storage, FilesystemEventRepository(history / 'events/thread-status-v1'),
            journals['thread-status-v1'], journals['thread-create-v1'], journals['thread-delete-v1'])
        deletion = FilesystemThreadDeletion(storage, journals['thread-delete-v1'],
                                            status_operations=journals['thread-status-v1'],
                                            creation_operations=journals['thread-create-v1'])
        return cls(storage, changes, creation, deletion, FilesystemThreadUpdates(backend))

    def update_thread(self, thread_id, command, **identity):
        if self.updates is None:
            raise RuntimeError('Thread updates require an operation coordinator')
        return self.updates.execute(thread_id, command, **identity)

    def get(self, thread_id: str) -> Thread | None:
        """Load a Thread from persistent storage."""
        return self.storage.get(thread_id)

    def query(
        self,
        query: ThreadQuery,
    ) -> list[Thread] | list[tuple[Thread, object]]:
        """Query persisted Threads through the domain manager."""
        query.validate()
        if query.query_type is ThreadQueryType.GET_THREAD:
            thread = self.storage.get(query.thread_id)
            return [thread] if thread is not None else []
        threads = self.storage.list()

        return ThreadManager.query(
            threads,
            query,
        )

    def execute(
        self,
        request: ThreadRequest,
    ) -> list[Thread] | list[tuple[Thread, object]]:
        """Execute a deterministic Thread request."""
        return self.query(build_thread_query(request))


    def execute_envelope(self, envelope):
        """Execute an external request envelope targeting Threads."""
        from .request_envelope import build_thread_request

        request = build_thread_request(envelope)
        return self.execute(request)

    def change_status(self, thread_id, new_status, *, previous_revision, operation_id, event_id):
        """Execute a recoverable mutation when a coordinator is configured."""
        if self.operations is None:
            raise RuntimeError("Thread mutations require an operation coordinator")
        return self.operations.change_status(
            thread_id, new_status, previous_revision=previous_revision,
            operation_id=operation_id, event_id=event_id,
        )

    def create_linked(self, thread: Thread, information_id: str, *,
                      operation_id: str, event_id: str) -> Thread:
        """Create a linked Thread through the recoverable coordinator."""
        if self.creation is None:
            raise RuntimeError("linked Thread creation requires an operation coordinator")
        return self.creation.create(thread, information_id,
                                    operation_id=operation_id, event_id=event_id)

    def recover(self):
        if self.operations is None:
            raise RuntimeError("Thread recovery requires an operation coordinator")
        return self.operations.recover()

    def delete(self, thread_id: str, *, previous_revision: int, operation_id: str) -> None:
        if self.deletion is None:
            raise RuntimeError("Thread deletion requires an operation coordinator")
        self.deletion.delete(thread_id, previous_revision=previous_revision,
                             operation_id=operation_id)

    def recover_all(self):
        """Resume linked creations before status changes."""
        if self.creation is None or self.operations is None:
            raise RuntimeError("full Thread recovery requires both coordinators")
        creations = self.creation.recover()
        status_changes = self.operations.recover()
        result = {"creations": creations, "status_changes": status_changes}
        if self.updates is not None:
            result["thread-updates"] = self.updates.recover()
        if self.deletion is not None:
            result["deletions"] = self.deletion.recover()
        return result
