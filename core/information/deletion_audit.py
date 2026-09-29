"""Read-only audit of Information deletion requests and their files."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


def audit_deletions(engine_root: Path) -> dict:
    root = Path(engine_root)
    if not root.is_dir():
        raise ValueError(f"engine root is not a directory: {root}")
    persistent = root / "memory" / "persistent"
    requests = root / "memory" / "history" / "pending-delete"
    report = {"requests_checked": 0, "issues": []}
    if persistent.is_symlink():
        report["issues"].append({"request": "memory/persistent",
                                 "reason": "symlink_skipped"})
    if requests.is_symlink():
        report["issues"].append({"request": "memory/history/pending-delete",
                                 "reason": "symlink_skipped"})
    if report["issues"]:
        return report
    if not requests.is_dir():
        return report
    for path in sorted(requests.glob("*.json")):
        location = path.relative_to(root).as_posix()
        if path.is_symlink():
            reason = "symlink_skipped"
        else:
            try:
                record = json.loads(path.read_text(encoding="utf-8"))
                if (not isinstance(record, dict)
                        or record.get("information_id") != path.stem
                        or record.get("status") not in {"PENDING_DELETE", "APPLYING_DELETE", "DELETED", "CANCELLED"}
                        or type(record.get("revision")) is not int
                        or record["revision"] < 1
                        or not isinstance(record.get("operation_id"), str)
                        or not record["operation_id"]
                        or not isinstance(record.get("requested_by"), str)
                        or not record["requested_by"]
                        or not isinstance(record.get("reason"), str)
                        or not record["reason"]
                        or (record.get("status") == "APPLYING_DELETE"
                            and (not isinstance(record.get("content_sha256"), str)
                                 or not re.fullmatch(r"[0-9a-f]{64}", record["content_sha256"])))):
                    raise ValueError("invalid deletion request")
                report["requests_checked"] += 1
                information = persistent / f"{path.stem}.md"
                if information.is_symlink():
                    reason = "symlink_skipped"
                elif record["status"] == "APPLYING_DELETE":
                    reason = "deletion_requires_resume"
                elif record["status"] == "PENDING_DELETE" and not information.is_file():
                    reason = "pending_without_information"
                elif record["status"] == "DELETED" and information.exists():
                    reason = "deleted_but_information_present"
                else:
                    reason = None
            except (OSError, UnicodeError, ValueError, TypeError):
                reason = "invalid_request"
        if reason:
            report["issues"].append({"request": location, "reason": reason})
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Read-only audit of deletion requests")
    parser.add_argument("--root", type=Path, required=True, help="Engine root containing memory/")
    args = parser.parse_args(argv)
    try:
        report = audit_deletions(args.root)
    except ValueError as exc:
        parser.error(str(exc))
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return int(bool(report["issues"]))


if __name__ == "__main__":
    raise SystemExit(main())
