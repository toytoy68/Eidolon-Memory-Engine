"""Fail closed when a historical writer would share persistent core data."""

from __future__ import annotations

from pathlib import Path


def require_legacy_persistent_only(persistent_root: Path, history_root: Path) -> None:
    """Call under the persistent writer lock before a legacy persistent mutation."""
    persistent = Path(persistent_root)
    history = Path(history_root)
    if persistent.is_symlink():
        raise ValueError("legacy writer blocked: persistent directory is a symlink")
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
    if threads.is_symlink() or (threads.is_dir() and any(threads.glob("*.md"))):
        raise ValueError("legacy writer blocked: core Thread storage exists")
    for name in ("thread-create-v1", "thread-status-v1"):
        operations = history / "operations" / name
        if operations.is_symlink() or (operations.is_dir() and any(operations.iterdir())):
            raise ValueError("legacy writer blocked: core operation journal exists")
