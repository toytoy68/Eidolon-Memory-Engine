"""Deterministic source manifest; an index can be rebuilt from these files."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
import re
from pathlib import Path

from core.backend.filesystem import FilesystemBackend
from core.backend.errors import InvalidMemory
from core.persistence import has_symlink_component


@dataclass(frozen=True)
class SourceEntry:
    information_id: str
    revision: int
    file_sha256: str


@dataclass(frozen=True)
class IndexManifest:
    entries: tuple[SourceEntry, ...]
    digest: str


@dataclass(frozen=True)
class IndexDelta:
    upsert: tuple[SourceEntry, ...]
    delete_ids: tuple[str, ...]


def diff_manifests(previous: IndexManifest, current: IndexManifest) -> IndexDelta:
    """Plan index changes from two validated source snapshots; perform no writes."""
    _validate_manifest(previous)
    _validate_manifest(current)
    old = {entry.information_id: entry for entry in previous.entries}
    new = {entry.information_id: entry for entry in current.entries}
    if len(old) != len(previous.entries) or len(new) != len(current.entries):
        raise ValueError("manifest contains duplicate Information identities")
    return IndexDelta(
        upsert=tuple(new[key] for key in sorted(new) if old.get(key) != new[key]),
        delete_ids=tuple(sorted(old.keys() - new.keys())),
    )


def _digest(entries: tuple[SourceEntry, ...]) -> str:
    payload = json.dumps(
        [[entry.information_id, entry.revision, entry.file_sha256] for entry in entries],
        ensure_ascii=False, separators=(",", ":"),
    ).encode("utf-8")
    return sha256(payload).hexdigest()


def _validate_manifest(manifest: IndexManifest) -> None:
    if not isinstance(manifest, IndexManifest) or not isinstance(manifest.entries, tuple):
        raise ValueError("invalid manifest")
    seen = set()
    for entry in manifest.entries:
        if (not isinstance(entry, SourceEntry)
                or not isinstance(entry.information_id, str)
                or not re.fullmatch(r"[A-Za-z0-9._-]+", entry.information_id)
                or type(entry.revision) is not int or entry.revision < 1
                or not isinstance(entry.file_sha256, str)
                or not re.fullmatch(r"[0-9a-f]{64}", entry.file_sha256)):
            raise ValueError("invalid manifest entry")
        if entry.information_id in seen:
            raise ValueError("manifest contains duplicate Information identities")
        seen.add(entry.information_id)
    if manifest.digest != _digest(manifest.entries):
        raise ValueError("manifest digest mismatch")


def build_manifest(persistent_root: Path) -> IndexManifest:
    """Read canonical files once; fail if any Information cannot be indexed safely."""
    root = Path(persistent_root)
    if has_symlink_component(root) or not root.is_dir():
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
        if (not re.fullmatch(r"[A-Za-z0-9._-]+", path.stem)
                or type(memory.revision) is not int or memory.revision < 1):
            raise InvalidMemory("Information manifest identity or revision is invalid")
        entries.append(SourceEntry(path.stem, memory.revision, sha256(raw).hexdigest()))
    frozen = tuple(entries)
    return IndexManifest(frozen, _digest(frozen))
