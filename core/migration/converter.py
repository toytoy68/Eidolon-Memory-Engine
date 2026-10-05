# ==========================================================
# Projet      : Eidolon Memory Engine
# Organisation: Eidolon Core Technologies (ECT)
# Fichier     : core/migration/converter.py
# Description : Explicit migration to a separate core tree; source is never modified.
# Standard    : Eidolon Presentation Standard v1
# ==========================================================

"""Explicit migration to a separate core tree; source is never modified."""

from __future__ import annotations

import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
from tempfile import NamedTemporaryFile

from core.backend.filesystem import FilesystemBackend
from core.migration.preflight import inspect_legacy_information
from core.migration.inventory import classify
from core.migration.simulation import _candidate_issues, preview_legacy_information
from core.persistence import has_symlink_component


def _atomic_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with NamedTemporaryFile(dir=path.parent, prefix=f".{path.name}.", delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def operational_import_blockers(source: Path) -> list[dict]:
    """Inspect a stopped source before creating or touching the destination.

    Only legacy records directly under operations are archival input. Versioned
    journals and receipts carry live invariants, including terminal reservations.
    Do not decode their payloads or descend through symbolic links.
    """
    blockers = []

    def block(path):
        blockers.append({"file": path.relative_to(source).as_posix(),
                         "reason": "operational_state_requires_import_policy",
                         "action_suggested": "Use a dedicated operational import; do not activate an archival copy"})

    def visit(path, *, legacy_root=False):
        if path.is_symlink():
            block(path)
        elif not path.exists():
            return
        elif not path.is_dir():
            block(path)
        else:
            for child in sorted(path.iterdir()):
                if child.is_symlink():
                    block(child)
                elif child.is_dir():
                    visit(child)
                elif child.name == '.write.lock' and child.is_file():
                    continue
                elif (legacy_root and child.suffix == '.json'
                      and classify(child, 'operations') == 'legacy_operation'):
                    continue
                else:
                    block(child)

    history = source / 'memory/history'
    for name in ('pending-delete', 'operation-receipts', 'operations'):
        visit(history / name, legacy_root=name == 'operations')
    # Preserved sources are active artifacts, never silently demote to archives.
    visit(source / 'memory/sources')
    return sorted(blockers, key=lambda item: item['file'])


def convert(source: Path, destination: Path) -> dict:
    source, destination = Path(source).absolute(), Path(destination).absolute()
    if (not source.is_dir() or has_symlink_component(source)
            or has_symlink_component(destination)
            or source == destination or source in destination.parents
            or destination in source.parents):
        raise ValueError("source and destination must be separate real trees")
    persistent = source / "memory/persistent"
    if has_symlink_component(persistent) or has_symlink_component(source / "memory/history"):
        raise ValueError("source memory tree contains a symlinked directory")
    if not persistent.is_dir():
        raise ValueError("source has no memory/persistent directory")
    blockers = operational_import_blockers(source)
    if blockers:
        # Return the report to the caller/CLI. Even migration-report.json would
        # violate the guarantee that an existing destination stays untouched.
        return {"converted": 0, "archived_events": 0, "archived_reviews": 0,
                "archived_other": 0, "rejected": blockers,
                "source": str(source), "destination": str(destination),
                "policy": "separate_destination_no_source_writes",
                "blocked_before_writes": True}
    destination.mkdir(parents=True, exist_ok=True)
    target = FilesystemBackend(destination / "memory/persistent", destination / "memory/history")
    rejected = []

    def reject(path: Path, reason: str, action: str) -> None:
        rejected.append({"file": path.relative_to(source).as_posix(),
                         "reason": reason, "action_suggested": action})

    candidates = {}
    for path in sorted(persistent.glob("*.md")):
        if path.is_symlink() or not path.is_file():
            reject(path, "unsafe_path", "Replace the link on an isolated copy and review its target")
            continue
        reasons = inspect_legacy_information(path)
        if not reasons:
            reasons = _candidate_issues(path, persistent)
        if reasons:
            reject(path, ",".join(reasons), "Review the original document and resolve the mapping on a copy")
            continue
        memory = preview_legacy_information(path)
        target_path = target._path(memory.information_id)
        try:
            expected = target._serialize_checked(memory).encode("utf-8")
            if target_path.is_symlink() or (target_path.exists() and target_path.read_bytes() != expected):
                reject(path, "destination_conflict", "Review destination and use a new empty tree")
                continue
        except (OSError, ValueError, TypeError) as exc:
            reject(path, type(exc).__name__, "Review the document and retry on an isolated copy")
            continue
        candidates[path.stem] = (path, memory, expected)

    blocked = {Path(item["file"]).stem for item in rejected}
    while True:
        dependent = []
        for identity, (path, memory, _) in candidates.items():
            if any((relation.get("target_id") or relation.get("target")) in blocked
                   for relation in memory.relations):
                dependent.append(identity)
        if not dependent:
            break
        for identity in dependent:
            path, _, _ = candidates.pop(identity)
            reject(path, "relation_target_rejected", "Resolve the target document first")
            blocked.add(identity)

    converted = 0
    for identity, (path, memory, expected) in sorted(candidates.items()):
        target_path = target._path(identity)
        try:
            if target_path.is_symlink() or (target_path.exists() and target_path.read_bytes() != expected):
                reject(path, "destination_conflict", "Review destination and use a new empty tree")
            elif not target_path.exists():
                target.store(memory)
                converted += 1
            else:
                converted += 1
        except (OSError, ValueError, TypeError) as exc:
            reject(path, type(exc).__name__, "Review the document and retry on an isolated copy")

    archived_events = archived_reviews = archived_other = 0
    # Preserve every other file, including historical operations and Working
    # memory, without interpreting it as a core document.
    for path in sorted((source / "memory").rglob("*")):
        if path.is_dir() and not path.is_symlink():
            continue
        relative = path.relative_to(source / "memory")
        if path.parent == persistent and path.suffix == ".md":
            continue  # converted or explicitly rejected above
        if path.is_symlink() or not path.is_file():
            reject(path, "unsafe_archive_path", "Review and copy manually after resolving the link")
            continue
        archive = destination / "archive" / relative
        raw = path.read_bytes()
        if archive.is_symlink() or (archive.exists() and archive.read_bytes() != raw):
            reject(path, "archive_conflict", "Review archive and use a new destination")
            continue
        if not archive.exists():
            _atomic_bytes(archive, raw)
        parts = relative.parts
        if parts[:2] == ("history", "events"):
            archived_events += 1
        elif parts[:2] == ("history", "reviews"):
            archived_reviews += 1
        else:
            archived_other += 1

    report = {"converted": converted, "archived_events": archived_events,
              "archived_reviews": archived_reviews, "archived_other": archived_other,
              "rejected": sorted(rejected, key=lambda item: item["file"]),
              "source": str(source), "destination": str(destination),
              "policy": "separate_destination_no_source_writes"}
    report_path = destination / "migration-report.json"
    payload = (json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")
    if not report_path.exists() or report_path.read_bytes() != payload:
        _atomic_bytes(report_path, payload)
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--destination", type=Path, required=True)
    args = parser.parse_args(argv)
    report = convert(args.source, args.destination)
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return int(bool(report["rejected"]))


if __name__ == "__main__":
    raise SystemExit(main())
