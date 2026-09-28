"""Create Threads with a verified link to a persisted Information."""

from __future__ import annotations

from dataclasses import replace

from core.backend.filesystem import FilesystemBackend
from core.persistence import exclusive_write
from core.threads.manager import ThreadManager, ThreadError
from core.threads.models import Thread
from core.threads.storage import ThreadStorage


class MissingLinkedInformation(ThreadError):
    """The requested Information does not exist at Thread creation time."""


class ThreadInformationLinkService:
    def __init__(self, backend: FilesystemBackend, storage: ThreadStorage) -> None:
        if backend.persistent_root.resolve() != storage.persistent_root.resolve():
            raise ValueError("Information and Thread stores must share a persistent root")
        self.backend = backend
        self.storage = storage

    def create(self, thread: Thread, information_id: str) -> Thread:
        """Verify the target and persist a CONCERNS link with the new Thread."""
        linked = self.prepare(thread, information_id)
        # Backend deletions hold this same root lock. Hold it through Thread
        # creation so the target cannot disappear between the check and write.
        with exclusive_write(self.backend.persistent_root):
            if self.backend.get(information_id) is None:
                raise MissingLinkedInformation(information_id)
            self.storage.create(linked)
        return linked

    @staticmethod
    def prepare(thread: Thread, information_id: str) -> Thread:
        """Build a validated linked snapshot without writing to storage."""
        if not isinstance(information_id, str) or not information_id:
            raise ValueError("information_id is required")
        ThreadManager.validate(thread)
        if any(not isinstance(relation, dict) for relation in thread.relations):
            raise ValueError("Thread relations must be objects")
        link = {"type": "CONCERNS", "target_id": information_id}
        relations = list(thread.relations)
        if link not in relations:
            relations.append(link)
        return replace(thread, relations=relations)
