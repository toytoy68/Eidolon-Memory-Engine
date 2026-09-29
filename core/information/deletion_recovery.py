"""Explicit, guarded recovery of interrupted core Information deletions."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from core.backend.errors import BackendError
from core.backend.filesystem import FilesystemBackend
from core.information.deletion_audit import audit_deletions
from core.persistence import has_symlink_component
from core.threads.storage import ThreadStorageError


def recover_deletions(engine_root: Path) -> dict:
    """Resume only durable APPLYING_DELETE receipts; never infer legacy deletions."""
    root = Path(engine_root)
    if has_symlink_component(root):
        return {"recovered": [], "blocked": [
            {"path": ".", "reason": "symlink_directory"}]}
    if not root.is_dir():
        raise ValueError(f"engine root is not a directory: {root}")
    persistent = root / "memory/persistent"
    history = root / "memory/history"
    pending = history / "pending-delete"
    report = {"recovered": [], "blocked": []}
    if (root.joinpath("memory").is_symlink() or history.is_symlink()
            or pending.is_symlink() or persistent.is_symlink()):
        report["blocked"].append({"path": "memory", "reason": "symlink_directory"})
        return report
    if not pending.is_dir():
        return report
    if not persistent.is_dir():
        report["blocked"].append({"path": "memory/persistent", "reason": "missing_directory"})
        return report
    backend = FilesystemBackend(persistent, history)
    for path in sorted(pending.glob("*.json")):
        relative = path.relative_to(root).as_posix()
        try:
            request = backend._load_delete_request(path, path.stem)
            if request["status"] != "APPLYING_DELETE":
                continue
            backend.approve_delete(path.stem, request["operation_id"])
            report["recovered"].append(relative)
        except (OSError, UnicodeError, ValueError, TypeError,
                BackendError, ThreadStorageError) as exc:
            report["blocked"].append({"path": relative, "reason": type(exc).__name__})
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit or explicitly resume Information deletion")
    parser.add_argument("--root", type=Path, required=True, help="Engine root containing memory/")
    parser.add_argument("--apply", action="store_true", help="Resume APPLYING_DELETE receipts")
    args = parser.parse_args(argv)
    try:
        report = recover_deletions(args.root) if args.apply else audit_deletions(args.root)
    except ValueError as exc:
        parser.error(str(exc))
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return int(bool(report.get("blocked") or report.get("issues")))


if __name__ == "__main__":
    raise SystemExit(main())
