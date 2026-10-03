"""Classify known runtime files without invoking writers or changing data."""

from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path

from core.persistence import has_symlink_component
from core.storage_format import decode_json_value


SOURCES = (
    ("lifecycle_triggers", "memory/history/operations/lifecycle-trigger-v1", "*.json"),
    ("routing_executions", "memory/history/operations/routing-execution-v1", "*.json"),
    ("working", "memory/working", "*.md"),
    ("information", "memory/persistent", "*.md"),
    ("threads", "memory/persistent/threads", "*.md"),
    ("events", "memory/history/events", "*.md"),
    ("thread_update_events", "memory/history/events/thread-update-v1", "*.md"),
    ("thread_update_operations", "memory/history/operations/thread-update-v1", "*.json"),
    ("thread_status_events", "memory/history/events/thread-status-v1", "*.md"),
    ("thread_create_events", "memory/history/events/thread-create-v1", "*.md"),
    ("information_write_events", "memory/history/events/information-write-v1", "*.md"),
    ("information_write_operations", "memory/history/operations/information-write-v1", "*.json"),
    ("information_write_receipts", "memory/history/operation-receipts/information-write-v1", "*.json"),
    ("reviews", "memory/history/reviews", "*.md"),
    ("operations", "memory/history/operations", "*.json"),
    ("thread_status_operations", "memory/history/operations/thread-status-v1", "*.json"),
    ("thread_create_operations", "memory/history/operations/thread-create-v1", "*.json"),
    ("thread_delete_operations", "memory/history/operations/thread-delete-v1", "*.json"),
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


def invalid_directory_ancestor(root: Path, path: Path) -> Path | None:
    """Find a file occupying an expected directory below the engine root."""
    current = root
    for part in path.relative_to(root).parts:
        current = current / part
        if current.exists() and not current.is_dir():
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
            if category == "routing_executions":
                version = data.get('format_version')
                return f"routing_execution_v{version}" if type(version) is int and version in {1, 2, 3, 4, 5} else "unknown"
            if category == "lifecycle_triggers":
                return "lifecycle_trigger_v1" if type(data.get("format_version")) is int and data['format_version'] == 1 else "unknown"
            if category == "pending_delete":
                return "pending_delete" if "information_id" in data else "unknown"
            if category == "information_write_receipts":
                return "core_information_receipt_v1" if data.get("format_version") == 1 else "unknown"
            if data.get("operation_type") in {"THREAD_STATUS_CHANGE", "THREAD_UPDATE", "THREAD_CREATE", "THREAD_DELETE", "INFORMATION_CREATE", "INFORMATION_UPDATE"}:
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


def unknown_history_entries(root: Path) -> list[dict]:
    """Report unregistered history paths, never descending through a symlink.

    A registered family owns only its direct files, not arbitrary subfolders.
    Archives live outside memory/history and are not active journals.
    """
    history = root / "memory/history"
    if symlink_ancestor(root, history) or invalid_directory_ancestor(root, history):
        return []  # Reported by the category scan; do not inspect descendants.
    patterns = {Path(relative): pattern for _, relative, pattern in SOURCES
                if relative.startswith("memory/history/")}
    directories = {Path("memory/history")}
    for directory in patterns:
        directories.add(directory)
        directories.update(parent for parent in directory.parents
                           if parent != Path(".") and parent != Path("memory"))
    issues = []

    def walk(directory):
        if not directory.exists():
            return
        for path in sorted(directory.iterdir()):
            relative = path.relative_to(root)
            parent_pattern = patterns.get(relative.parent)
            registered_file = parent_pattern is not None and path.match(parent_pattern)
            if path.is_symlink():
                # Registered paths are reported by the category scanner.
                if relative not in directories and not registered_file:
                    issues.append({"path": relative.as_posix(), "reason": "symlink_skipped"})
            elif path.is_dir():
                if relative in directories:
                    walk(path)
                else:
                    issues.append({"path": relative.as_posix(), "reason": "unknown_history_directory"})
            elif relative in directories:
                continue  # invalid_directory is reported by the category scan.
            elif path.name == ".write.lock" and relative.parent in patterns and path.is_file():
                continue  # Cooperative lock inode, not a journal record.
            elif not registered_file:
                issues.append({"path": relative.as_posix(), "reason": "unknown_history_file"})

    walk(history)
    return issues


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
            invalid = invalid_directory_ancestor(root, directory)
            if invalid is not None:
                location = invalid.relative_to(root).as_posix()
                if location not in invalid_directories:
                    result["needs_review"].append({
                        "path": location, "reason": "invalid_directory"})
                    invalid_directories.add(location)
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
    result["needs_review"].extend(unknown_history_entries(root))
    from core.information.write_audit import audit_information_writes
    result["information_writes"] = audit_information_writes(root)
    for issue in result["information_writes"]["issues"]:
        result["needs_review"].append({"path": "memory/history/information-write-v1",
                                     "reason": issue["reason"], "operation_id": issue["operation_id"]})
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
