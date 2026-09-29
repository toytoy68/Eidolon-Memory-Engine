"""Deterministic source manifest; an index can be rebuilt from these files."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path

from core.backend.filesystem import FilesystemBackend
from core.backend.errors import InvalidMemory


@dataclass(frozen=True)
class SourceEntry:
    information_id: str
    revision: int
    file_sha256: str


@dataclass(frozen=True)
class IndexManifest:
    entries: tuple[SourceEntry, ...]
    digest: str


def build_manifest(persistent_root: Path) -> IndexManifest:
    """Read canonical files once; fail if any Information cannot be indexed safely."""
    root = Path(persistent_root)
    if root.is_symlink() or not root.is_dir():
        raise ValueError("persistent root must be a real directory")
    entries = []
    for path in sorted(root.glob("*.md")):
        if path.is_symlink() or not path.is_file():
            raise InvalidMemory("Information manifest contains an unsafe path")
        try:
            raw = path.read_bytes()
            memory = FilesystemBackend._deserialize(raw.decode("utf-8"))
        except (OSError, UnicodeError) as exc:
            raise InvalidMemory("Information manifest contains an unreadable file") from exc
        if memory.information_id != path.stem:
            raise InvalidMemory("Information manifest identity mismatch")
        entries.append(SourceEntry(path.stem, memory.revision, sha256(raw).hexdigest()))
    payload = json.dumps(
        [[entry.information_id, entry.revision, entry.file_sha256] for entry in entries],
        ensure_ascii=False, separators=(",", ":"),
    ).encode("utf-8")
    return IndexManifest(tuple(entries), sha256(payload).hexdigest())
