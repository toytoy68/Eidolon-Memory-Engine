# ==========================================================
# Projet      : Eidolon Memory Engine
# Organisation: Eidolon Core Technologies (ECT)
# Fichier     : core/information/relation_audit.py
# Description : Read-only inventory of core Information relation target shapes.
# Standard    : Eidolon Presentation Standard v1
# ==========================================================

"""Read-only inventory of core Information relation target shapes."""

from __future__ import annotations

import argparse
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
import re

from core.backend.errors import InvalidMemory
from core.backend.filesystem import FilesystemBackend
from core.indexing import build_manifest
from core.persistence import has_symlink_component


def audit_relations(persistent_root: Path, *, history_root: Path | None = None) -> dict:
    """Count targets without assuming every relation points to an Information."""
    root = Path(persistent_root)
    if has_symlink_component(root):
        raise ValueError("relation source contains a symlinked directory")
    receipts = Path(history_root) / "pending-delete" if history_root is not None else None
    if receipts is not None and has_symlink_component(receipts):
        raise ValueError("deletion receipt source contains a symlinked directory")
    if receipts is not None and any(
        directory.exists() and not directory.is_dir()
        for directory in (receipts.parent, receipts)
    ):
        raise InvalidMemory("deletion receipt source is not a directory")
    manifest = build_manifest(root)
    known_ids = {entry.information_id for entry in manifest.entries}
    counts: Counter[str] = Counter()
    for entry in manifest.entries:
        path = root / f"{entry.information_id}.md"
        if path.is_symlink():
            raise InvalidMemory("relation source contains a symlinked file")
        raw = path.read_bytes()
        if sha256(raw).hexdigest() != entry.file_sha256:
            raise InvalidMemory("relation source changed during audit")
        memory = FilesystemBackend._deserialize(raw.decode("utf-8"))
        if memory.information_id != entry.information_id:
            raise InvalidMemory("relation source identity changed")
        for relation in memory.relations:
            if not isinstance(relation, dict):
                counts["invalid"] += 1
                continue
            target_id = relation.get("target_id")
            legacy_target = relation.get("target")
            if target_id is not None and legacy_target is not None and target_id != legacy_target:
                counts["ambiguous"] += 1
                continue
            target = target_id if target_id is not None else legacy_target
            if not isinstance(target, str) or not target:
                counts["invalid"] += 1
            elif target == entry.information_id:
                counts["self"] += 1
            elif target in known_ids:
                counts["information_target"] += 1
            elif receipts is not None and re.fullmatch(r"[A-Za-z0-9._-]+", target):
                receipt = receipts / f"{target}.json"
                if receipt.is_symlink():
                    raise InvalidMemory("relation target deletion receipt is a symlink")
                if receipt.exists():
                    FilesystemBackend._load_delete_request(receipt, target)
                    counts["reserved_information_target"] += 1
                else:
                    counts["external_or_missing"] += 1
            else:
                counts["external_or_missing"] += 1
    return {"information_count": len(manifest.entries),
            "source_digest": manifest.digest,
            "relations": dict(sorted(counts.items())),
            "policy": "read_only_no_target_type_inferred"}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Read-only core Information relation audit")
    parser.add_argument("--root", type=Path, required=True,
                        help="Stopped engine copy containing memory/persistent")
    args = parser.parse_args(argv)
    try:
        report = audit_relations(args.root / "memory/persistent",
                                 history_root=args.root / "memory/history")
    except (OSError, UnicodeError, ValueError, InvalidMemory) as exc:
        parser.error(str(exc))
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
