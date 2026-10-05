# ==========================================================
# Projet      : Eidolon Memory Engine
# Organisation: Eidolon Core Technologies (ECT)
# Fichier     : tools/writer_inventory.py
# Description : Read-only hints about running and configured Memory Engine writers on Linux.
# Standard    : Eidolon Presentation Standard v1
# ==========================================================

"""Read-only hints about running and configured Memory Engine writers on Linux.

This is a heuristic inventory, not proof that every writer is stopped. Inspect
systemd, cron, user sessions and application services manually on the VM.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path


MARKERS = (
    "memory_controller.py", "memory_relation_engine.py",
    "eidolon-memory-relations", "core.operations.cli",
    "eidolon-memory-controller",
)


def _marker(value: str) -> str | None:
    return next((marker for marker in MARKERS if marker in value), None)


def discover_writers(*, proc_root: Path = Path("/proc"),
                     unit_dirs: tuple[Path, ...] = (Path("/etc/systemd/system"),
                                                      Path("/usr/lib/systemd/system"),
                                                      Path("/lib/systemd/system")),
                     cron_paths: tuple[Path, ...] = (Path("/etc/crontab"),
                                                       Path("/etc/cron.d"),
                                                       Path("/var/spool/cron/crontabs"))) -> dict:
    """Return possible writers without exposing their full arguments or files."""
    running: list[dict] = []
    configured: list[dict] = []
    unreadable: list[str] = []
    if proc_root.is_dir():
        for process in sorted(proc_root.iterdir(), key=lambda path: path.name):
            if not process.name.isdigit():
                continue
            if int(process.name) == os.getpid():
                continue
            try:
                command = (process / "cmdline").read_bytes().replace(b"\0", b" ").decode(
                    "utf-8", errors="replace")
            except (OSError, PermissionError):
                unreadable.append(f"proc/{process.name}/cmdline")
                continue
            matched = _marker(command)
            if matched:
                running.append({"pid": int(process.name), "marker": matched})

    locations = []
    for directory in unit_dirs:
        if directory.is_dir():
            locations.extend(path for path in directory.rglob("*")
                             if path.suffix in {".service", ".timer", ".socket"})
    for entry in cron_paths:
        try:
            if entry.is_dir():
                locations.extend(path for path in entry.iterdir() if path.is_file())
            elif entry.is_file():
                locations.append(entry)
        except OSError:
            # Cron spools can be visible but not searchable by this account.
            # Keep the partial inventory and make its missing coverage explicit.
            unreadable.append(str(entry))
    for path in sorted(set(locations)):
        try:
            content = path.read_text(encoding="utf-8", errors="replace")
        except (OSError, PermissionError):
            unreadable.append(str(path))
            continue
        matched = _marker(content)
        if matched:
            configured.append({"path": str(path), "marker": matched})
    return {"running": running, "configured": configured,
            "unreadable": sorted(unreadable),
            "coverage": "heuristic_manual_service_review_required"}


def main(argv: list[str] | None = None) -> int:
    argparse.ArgumentParser(description=__doc__).parse_args(argv)
    print(json.dumps(discover_writers(), ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
