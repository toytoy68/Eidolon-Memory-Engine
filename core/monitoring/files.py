# ==========================================================
# Projet      : Eidolon Memory Engine
# Organisation: Eidolon Core Technologies (ECT)
# Fichier     : core/monitoring/files.py
# Description : Allowlisted, read-only Markdown access for the dashboard.
# Standard    : Eidolon Presentation Standard v1
# ==========================================================

"""Allowlisted, read-only Markdown access for the dashboard."""

from __future__ import annotations

from pathlib import Path
import re


DIRECTORIES = {
    "working": "memory/working",
    "information": "memory/persistent",
    "threads": "memory/persistent/threads",
    "events": "memory/history/events",
    "thread-events": "memory/history/events/thread-status-v1",
    "reviews": "memory/history/reviews",
}
PAGE_SIZE = 100
MAX_DOCUMENT_BYTES = 1024 * 1024


def _directory(root: Path, category: str) -> Path:
    if category not in DIRECTORIES:
        raise ValueError("unknown category")
    root = Path(root)
    current = root
    for part in Path(DIRECTORIES[category]).parts:
        current = current / part
        if current.is_symlink():
            raise ValueError("linked directories are not browsable")
    return current


def list_documents(root: Path, category: str, offset: int = 0) -> list[str]:
    if offset < 0:
        raise ValueError("negative offset")
    directory = _directory(root, category)
    if not directory.is_dir():
        return []
    names = []
    for path in directory.glob("*.md"):
        if path.is_file() and not path.is_symlink():
            names.append(path.name)
    return sorted(names)[offset:offset + PAGE_SIZE]


def read_document(root: Path, category: str, name: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9._-]+\.md", name):
        raise ValueError("invalid document name")
    path = _directory(root, category) / name
    if path.is_symlink() or not path.is_file():
        raise ValueError("document unavailable")
    if path.stat().st_size > MAX_DOCUMENT_BYTES:
        raise ValueError("document exceeds preview limit")
    with path.open("rb") as handle:
        data = handle.read(MAX_DOCUMENT_BYTES + 1)
    if len(data) > MAX_DOCUMENT_BYTES:
        raise ValueError("document exceeds preview limit")
    return data.decode("utf-8")
