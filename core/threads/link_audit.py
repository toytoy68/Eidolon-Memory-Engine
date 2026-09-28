"""Read-only consistency audit of Thread links to Information files."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re

from core.backend.filesystem import FilesystemBackend
from core.backend.errors import InvalidMemory
from core.threads.storage import ThreadStorage, ThreadStorageError


def audit_links(engine_root: Path) -> dict:
    root = Path(engine_root)
    if not root.is_dir():
        raise ValueError(f"engine root is not a directory: {root}")
    persistent = root / "memory" / "persistent"
    threads = persistent / "threads"
    report = {"threads_checked": 0, "links_checked": 0, "issues": []}
    if persistent.is_symlink() or threads.is_symlink():
        report["issues"].append({"thread": "memory/persistent/threads", "reason": "symlink_skipped"})
        return report
    if not threads.is_dir():
        return report
    for path in sorted(threads.glob("*.md")):
        location = path.relative_to(root).as_posix()
        if path.is_symlink():
            report["issues"].append({"thread": location, "reason": "symlink_skipped"})
            continue
        try:
            thread = ThreadStorage._deserialize(path.read_text(encoding="utf-8"))
            if thread.thread_id != path.stem:
                raise ValueError("identity mismatch")
        except (OSError, UnicodeError, ValueError, TypeError, KeyError, AttributeError,
                ThreadStorageError):
            report["issues"].append({"thread": location, "reason": "invalid_thread"})
            continue
        report["threads_checked"] += 1
        for relation in thread.relations:
            if not isinstance(relation, dict) or relation.get("type") != "CONCERNS":
                continue
            report["links_checked"] += 1
            target = relation.get("target_id", relation.get("target"))
            if (not isinstance(target, str)
                    or not re.fullmatch(r"[A-Za-z0-9._-]+", target)):
                reason = "invalid_target_id"
            else:
                information = persistent / f"{target}.md"
                if information.is_symlink():
                    reason = "symlink_skipped"
                elif not information.is_file():
                    reason = "missing_information"
                else:
                    try:
                        memory = FilesystemBackend._deserialize(
                            information.read_text(encoding="utf-8"))
                        reason = None if memory.information_id == target else "invalid_information"
                    except (OSError, UnicodeError, ValueError, TypeError, KeyError, AttributeError,
                            InvalidMemory):
                        reason = "invalid_information"
            if reason:
                report["issues"].append({"thread": location, "reason": reason})
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Read-only audit of Thread Information links")
    parser.add_argument("--root", type=Path, required=True, help="Engine root containing memory/")
    args = parser.parse_args(argv)
    try:
        report = audit_links(args.root)
    except ValueError as exc:
        parser.error(str(exc))
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return int(bool(report["issues"]))


if __name__ == "__main__":
    raise SystemExit(main())
