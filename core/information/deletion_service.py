"""Guard Information deletion when persisted Threads refer to it."""

from __future__ import annotations

from core.backend.errors import BackendError
from core.backend.filesystem import FilesystemBackend
from core.persistence import exclusive_write
from core.threads.storage import ThreadStorage, ThreadStorageError


class InformationDeletionBlocked(BackendError):
    """Deletion needs review because a Thread link or unreadable Thread exists."""


class LinkedInformationDeletionService:
    def __init__(self, backend: FilesystemBackend, threads: ThreadStorage) -> None:
        if backend.persistent_root.resolve() != threads.persistent_root.resolve():
            raise ValueError("Information and Thread stores must share a persistent root")
        self.backend = backend
        self.threads = threads

    def approve_delete(self, information_id: str, operation_id: str):
        """Approve a pending deletion only when no Thread currently links to it."""
        self.backend._validate_id(information_id)
        # Same lock order as ThreadInformationLinkService: persistent -> threads.
        with exclusive_write(self.backend.persistent_root):
            with exclusive_write(self.threads.threads_root):
                for path in sorted(self.threads.threads_root.glob("*.md")):
                    if path.is_symlink():
                        raise InformationDeletionBlocked("linked Thread scan contains a symlink")
                    try:
                        thread = ThreadStorage._deserialize(path.read_text(encoding="utf-8"))
                        if thread.thread_id != path.stem:
                            raise ValueError("Thread identity mismatch")
                    except (OSError, UnicodeError, ValueError, TypeError, KeyError,
                            AttributeError, ThreadStorageError) as exc:
                        raise InformationDeletionBlocked(
                            "unreadable Thread prevents safe Information deletion"
                        ) from exc
                    for relation in thread.relations:
                        if not isinstance(relation, dict):
                            raise InformationDeletionBlocked("invalid Thread relation")
                        if (relation.get("type") == "CONCERNS"
                                and relation.get("target_id", relation.get("target")) == information_id):
                            raise InformationDeletionBlocked(
                                f"Information is linked by Thread {thread.thread_id}"
                            )
                return self.backend.approve_delete(information_id, operation_id)
