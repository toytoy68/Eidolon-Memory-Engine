# ==========================================================
# Projet      : Eidolon Memory Engine
# Organisation: Eidolon Core Technologies (ECT)
# Fichier     : core/monitoring/metrics.py
# Description : Host and memory-tree measurements without opening memory contents.
# Standard    : Eidolon Presentation Standard v1
# ==========================================================

"""Host and memory-tree measurements without opening memory contents."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import socket


def memory_bytes(meminfo_path: Path = Path("/proc/meminfo")) -> dict[str, int]:
    values = {}
    for line in meminfo_path.read_text(encoding="ascii").splitlines():
        name, _, value = line.partition(":")
        if name in {"MemTotal", "MemAvailable"}:
            amount, unit = value.strip().split()
            if unit != "kB":
                raise ValueError("unexpected meminfo unit")
            values[name] = int(amount) * 1024
    if not {"MemTotal", "MemAvailable"} <= values.keys():
        raise ValueError("incomplete meminfo")
    if not 0 <= values["MemAvailable"] <= values["MemTotal"]:
        raise ValueError("invalid meminfo values")
    return {"total": values["MemTotal"], "available": values["MemAvailable"],
            "used": values["MemTotal"] - values["MemAvailable"]}


def tree_bytes(root: Path) -> dict[str, int]:
    """Count regular files without following links or reading their contents."""
    result = {"files": 0, "bytes": 0, "symlinks_skipped": 0}
    if root.is_symlink():
        result["symlinks_skipped"] = 1
        return result
    if not root.is_dir():
        return result
    seen = set()

    def visit(directory):
        with os.scandir(directory) as entries:
            for entry in entries:
                if entry.is_symlink():
                    result["symlinks_skipped"] += 1
                elif entry.is_dir(follow_symlinks=False):
                    visit(entry.path)
                elif entry.is_file(follow_symlinks=False):
                    stat = entry.stat(follow_symlinks=False)
                    identity = (stat.st_dev, stat.st_ino)
                    if identity not in seen:
                        seen.add(identity)
                        result["files"] += 1
                        result["bytes"] += stat.st_size

    visit(root)
    return result


def collect_metrics(engine_root: Path, *, meminfo_path: Path = Path("/proc/meminfo")) -> dict:
    root = Path(engine_root)
    if not root.is_dir():
        raise ValueError(f"engine root is not a directory: {root}")
    data = root / "memory"
    if data.is_symlink():
        raise ValueError("memory root must not be a symlink")
    volume = data if data.is_dir() else root
    usage = shutil.disk_usage(volume)
    return {
        "host": socket.gethostname(),
        "measured_at": datetime.now(timezone.utc).isoformat(),
        "data_path": str(data.resolve()),
        "ram_bytes": memory_bytes(meminfo_path),
        "volume_bytes": {"total": usage.total, "used": usage.used, "free": usage.free},
        "engine_data": tree_bytes(data),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Read-only host and engine data metrics")
    parser.add_argument("--root", type=Path, required=True, help="Engine root containing memory/")
    args = parser.parse_args(argv)
    try:
        result = collect_metrics(args.root)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
