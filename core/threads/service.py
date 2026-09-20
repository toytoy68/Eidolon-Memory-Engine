"""Application service for Eidolon Threads."""

from __future__ import annotations

from .manager import ThreadManager
from .models import Thread
from .queries import ThreadQuery
from .storage import ThreadStorage


class ThreadService:
    """Coordinate Thread persistence and domain queries."""

    def __init__(self, storage: ThreadStorage) -> None:
        self.storage = storage

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
