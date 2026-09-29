"""Read-only exact-content grouping for human consolidation review."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path

from core.backend.errors import InvalidMemory
from core.backend.filesystem import FilesystemBackend
from core.indexing import build_manifest
from core.persistence import has_symlink_component


@dataclass(frozen=True)
class DuplicateGroup:
    information_ids: tuple[str, ...]
    differing_fields: tuple[str, ...]


@dataclass(frozen=True)
class ConsolidationPreview:
    source_digest: str
    groups: tuple[DuplicateGroup, ...]


def preview_exact_duplicates(persistent_root: Path) -> ConsolidationPreview:
    """Return identity-only review groups from a stopped source copy; never write."""
    root = Path(persistent_root)
    if has_symlink_component(root):
        raise ValueError("consolidation source contains a symlinked directory")
    manifest = build_manifest(root)
    by_content = defaultdict(list)
    for entry in manifest.entries:
        path = root / f"{entry.information_id}.md"
        if path.is_symlink():
            raise InvalidMemory("consolidation source contains a symlinked file")
        raw = path.read_bytes()
        if sha256(raw).hexdigest() != entry.file_sha256:
            raise InvalidMemory("consolidation source changed during preview")
        memory = FilesystemBackend._deserialize(raw.decode("utf-8"))
        if memory.information_id != entry.information_id:
            raise InvalidMemory("consolidation source identity changed")
        if isinstance(memory.content, str) and memory.content:
            by_content[memory.content].append(memory)
    groups = []
    fields = ("revision", "metadata", "provenance", "temporal", "verification", "relations")
    for memories in by_content.values():
        if len(memories) < 2:
            continue
        first = memories[0]
        differences = tuple(field for field in fields
                            if any(getattr(memory, field) != getattr(first, field)
                                   for memory in memories[1:]))
        groups.append(DuplicateGroup(tuple(sorted(memory.information_id
                                                for memory in memories)), differences))
    groups.sort(key=lambda group: group.information_ids)
    return ConsolidationPreview(manifest.digest, tuple(groups))
