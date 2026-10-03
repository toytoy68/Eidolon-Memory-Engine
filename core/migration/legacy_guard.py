"""Fail closed when a historical writer would share persistent core data."""

from __future__ import annotations

from pathlib import Path

from core.persistence import has_symlink_component


def require_legacy_persistent_only(persistent_root: Path, history_root: Path) -> None:
    """Call under the persistent writer lock before a legacy persistent mutation."""
    persistent = Path(persistent_root)
    history = Path(history_root)
    if has_symlink_component(persistent) or has_symlink_component(history):
        raise ValueError("legacy writer blocked: storage directory contains a symlink")
    for path in persistent.glob("*.md"):
        if path.is_symlink():
            raise ValueError("legacy writer blocked: symlink in persistent Information")
        try:
            with path.open("rb") as handle:
                header = handle.read(96)
        except OSError as exc:
            raise ValueError("legacy writer blocked: unreadable persistent Information") from exc
        if header.startswith(b"# Eidolon Information Object"):
            raise ValueError("legacy writer blocked: core Information exists")
    threads = persistent / "threads"
    if has_symlink_component(threads) or (threads.is_dir() and any(threads.glob("*.md"))):
        raise ValueError("legacy writer blocked: core Thread storage exists")
    # Retained canonical history remains a boundary even with no visible objects.
    families = ("thread-create-v1", "thread-status-v1", "thread-update-v1",
                "thread-delete-v1", "routing-execution-v1", "information-write-v1",
                "lifecycle-trigger-v1")
    directories = [history / category / name
                   for category in ("operations", "events", "operation-receipts")
                   for name in families]
    directories.append(history / "pending-delete")
    for journal in directories:
        if has_symlink_component(journal):
            raise ValueError("legacy writer blocked: core history journal contains a symlink")
        try:
            if journal.exists():
                if not journal.is_dir() or any(
                    entry.name != '.write.lock' or entry.is_symlink() or not entry.is_file()
                    for entry in journal.iterdir()
                ):
                    raise ValueError("legacy writer blocked: core operation journal exists")
        except OSError as exc:
            raise ValueError("legacy writer blocked: unreadable core history") from exc
