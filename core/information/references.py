"""Check persisted Thread references before removing an Information."""

from __future__ import annotations

from pathlib import Path

from core.backend.errors import InformationDeletionBlocked
from core.threads.storage import ThreadStorage, ThreadStorageError


def ensure_no_thread_links(threads_root: Path, information_id: str) -> None:
    """Fail closed on links or unreadable Threads; caller holds the writer lock."""
    if threads_root.is_symlink():
        raise InformationDeletionBlocked("Thread directory is a symlink")
    if not threads_root.is_dir():
        return
    for path in sorted(threads_root.glob("*.md")):
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
