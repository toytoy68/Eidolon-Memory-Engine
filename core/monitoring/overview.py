"""Read-only counts of current Thread and Operation journals."""

from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path

from core.storage_format import decode_document
from core.threads.models import ThreadStatus
from core.operations.models import OperationStatus


def _count_directory(directory: Path, root: Path, suffix: str, parse, allowed) -> dict:
    counts = Counter()
    issues = []
    if directory.is_symlink():
        return {"statuses": {}, "needs_review": [directory.relative_to(root).as_posix()]}
    if directory.is_dir():
        for path in sorted(directory.glob(f"*{suffix}")):
            if path.is_symlink():
                issues.append(path.relative_to(root).as_posix())
                continue
            if not path.is_file():
                continue
            try:
                status = parse(path)
                if status not in allowed:
                    raise ValueError("unknown status")
                counts[status] += 1
            except (OSError, UnicodeError, ValueError, TypeError, KeyError, AttributeError):
                issues.append(path.relative_to(root).as_posix())
    return {"statuses": dict(sorted(counts.items())), "needs_review": issues}


def _thread_status(path: Path) -> str:
    payload = decode_document(path.read_text(encoding="utf-8"), "Thread")
    if payload is None or payload.get("thread_id") != path.stem:
        raise ValueError("unsupported or mismatched Thread")
    return payload["status"]


def _operation_status(path: Path) -> str:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if (not isinstance(payload, dict) or payload.get("operation_id") != path.stem
            or payload.get("operation_type") != "THREAD_STATUS_CHANGE"):
        raise ValueError("unsupported or mismatched Operation")
    return payload["status"]


def overview(engine_root: Path) -> dict:
    root = Path(engine_root)
    if not root.is_dir():
        raise ValueError(f"engine root is not a directory: {root}")
    data = root / "memory"
    if data.is_symlink():
        raise ValueError("memory root must not be a symlink")
    threads = _count_directory(data / "persistent" / "threads", root, ".md",
                               _thread_status, {s.value for s in ThreadStatus})
    operations = _count_directory(data / "history" / "operations" / "thread-status-v1",
                                  root, ".json", _operation_status,
                                  {s.value for s in OperationStatus})
    return {"threads": threads, "thread_status_operations": operations,
            "pending_operations": sum(operations["statuses"].get(s, 0)
                                      for s in ("PREPARED", "APPLYING"))}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Read-only Thread and Operation overview")
    parser.add_argument("--root", type=Path, required=True, help="Engine root containing memory/")
    args = parser.parse_args(argv)
    try:
        result = overview(args.root)
    except ValueError as exc:
        parser.error(str(exc))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return int(bool(result["threads"]["needs_review"]
                    or result["thread_status_operations"]["needs_review"]))


if __name__ == "__main__":
    raise SystemExit(main())
