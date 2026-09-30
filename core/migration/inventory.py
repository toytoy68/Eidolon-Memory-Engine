"""Classify known runtime files without invoking writers or changing data."""

from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path

from core.persistence import has_symlink_component
from core.storage_format import decode_json_value


SOURCES = (
    ("working", "memory/working", "*.md"),
    ("information", "memory/persistent", "*.md"),
    ("threads", "memory/persistent/threads", "*.md"),
    ("events", "memory/history/events", "*.md"),
    ("thread_status_events", "memory/history/events/thread-status-v1", "*.md"),
    ("thread_create_events", "memory/history/events/thread-create-v1", "*.md"),
    ("reviews", "memory/history/reviews", "*.md"),
    ("operations", "memory/history/operations", "*.json"),
    ("thread_status_operations", "memory/history/operations/thread-status-v1", "*.json"),
    ("thread_create_operations", "memory/history/operations/thread-create-v1", "*.json"),
    ("pending_delete", "memory/history/pending-delete", "*.json"),
)


def symlink_ancestor(root: Path, path: Path) -> Path | None:
    """Return the first linked component below the engine root, without following it."""
    current = root
    for part in path.relative_to(root).parts:
        current = current / part
        if current.is_symlink():
            return current
    return None


def classify(path: Path, category: str) -> str:
    if path.is_symlink():
        return "symlink_skipped"
    try:
        if path.suffix == ".json":
            data = decode_json_value(path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                return "unknown"
            if category == "pending_delete":
                return "pending_delete" if "information_id" in data else "unknown"
            if data.get("operation_type") in {"THREAD_STATUS_CHANGE", "THREAD_CREATE"}:
                return "core_operation"
            if "operation_id" in data and "result" in data:
                return "legacy_operation"
            return "unknown"

        with path.open("r", encoding="utf-8") as handle:
            header = handle.read(4096)
    except (OSError, UnicodeError, ValueError):
        return "unreadable_or_invalid"

    for kind in ("Information", "Thread"):
        prefix = f"# Eidolon {kind} Object\n\nVersion: "
        if header.startswith(prefix):
            version = header[len(prefix):].splitlines()[0]
            return f"core_{kind.lower()}_{version}" if version in {"0.1", "0.2"} else "unknown"
    if header.startswith("# Eidolon Memory Event\n\nVersion: 0.2\n"):
        return "core_event_0.2"
    if header.startswith("---\n") or header.startswith("---\r\n"):
        return "legacy_front_matter"
    if category.endswith("events") and header.startswith("event_id:"):
        return "legacy_event_plain"
    return "unknown"


def inventory(engine_root: Path) -> dict:
    """Count recognized file shapes; never parse or expose memory content."""
    root = Path(engine_root)
    if has_symlink_component(root):
        raise ValueError("engine root contains a symlinked ancestor")
    if not root.is_dir():
        raise ValueError(f"engine root is not a directory: {root}")
    result = {"categories": {}, "needs_review": []}
    invalid_directories = set()
    for category, relative, pattern in SOURCES:
        directory = root / relative
        counts: Counter[str] = Counter()
        linked = symlink_ancestor(root, directory)
        if linked is not None:
            result["needs_review"].append({
                "path": linked.relative_to(root).as_posix(), "reason": "symlink_skipped"})
        else:
            current = root
            for part in Path(relative).parts:
                current = current / part
                if current.exists() and not current.is_dir():
                    location = current.relative_to(root).as_posix()
                    if location not in invalid_directories:
                        result["needs_review"].append({
                            "path": location, "reason": "invalid_directory"})
                        invalid_directories.add(location)
                    break
        if linked is None and directory.is_dir():
            for path in sorted(directory.glob(pattern)):
                if not path.is_file() and not path.is_symlink():
                    continue
                kind = classify(path, category)
                counts[kind] += 1
                if kind in {"unknown", "unreadable_or_invalid", "symlink_skipped"}:
                    result["needs_review"].append({
                        "path": path.relative_to(root).as_posix(), "reason": kind,
                    })
        result["categories"][category] = dict(sorted(counts.items()))
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Read-only inventory of memory file formats")
    parser.add_argument("--root", type=Path, required=True, help="Engine root containing memory/")
    args = parser.parse_args(argv)
    try:
        result = inventory(args.root)
    except ValueError as exc:
        parser.error(str(exc))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return int(bool(result["needs_review"]))


if __name__ == "__main__":
    raise SystemExit(main())
