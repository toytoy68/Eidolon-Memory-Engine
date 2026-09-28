"""Application service for Eidolon Threads."""

from __future__ import annotations

from .manager import ThreadManager
from .models import Thread
from .queries import ThreadQuery
from .request_mapping import build_thread_query
from .requests import ThreadRequest
from .storage import ThreadStorage


class ThreadService:
    """Coordinate Thread persistence and domain queries."""

    def __init__(self, storage: ThreadStorage, operations=None, creation=None) -> None:
        self.storage = storage
        self.operations = operations
        self.creation = creation

    def get(self, thread_id: str) -> Thread | None:
        """Load a Thread from persistent storage."""
        return self.storage.get(thread_id)

    def query(
        self,
        query: ThreadQuery,
    ) -> list[Thread] | list[tuple[Thread, object]]:
        """Query persisted Threads through the domain manager."""
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

    def recover_all(self):
        """Resume linked creations before status changes."""
        if self.creation is None or self.operations is None:
            raise RuntimeError("full Thread recovery requires both coordinators")
        creations = self.creation.recover()
        status_changes = self.operations.recover()
        return {"creations": creations, "status_changes": status_changes}
