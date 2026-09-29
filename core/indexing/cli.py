"""Read-only source manifest summary for stopped copies of engine data."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from core.backend.errors import InvalidMemory
from .manifest import build_manifest, diff_manifests


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Read-only Information index source summary")
    parser.add_argument("--root", type=Path, required=True,
                        help="Engine root containing memory/persistent")
    parser.add_argument("--compare-root", type=Path,
                        help="Newer engine copy to compare with --root")
    args = parser.parse_args(argv)
    try:
        source = build_manifest(args.root / "memory/persistent")
        report = {"source": {"count": len(source.entries), "digest": source.digest}}
        if args.compare_root is not None:
            current = build_manifest(args.compare_root / "memory/persistent")
            delta = diff_manifests(source, current)
            previous_ids = {entry.information_id for entry in source.entries}
            report["comparison"] = {
                "count": len(current.entries), "digest": current.digest,
                "added": sum(entry.information_id not in previous_ids for entry in delta.upsert),
                "updated": sum(entry.information_id in previous_ids for entry in delta.upsert),
                "removed": len(delta.delete_ids),
            }
    except (InvalidMemory, ValueError, OSError) as exc:
        parser.error(str(exc))
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
