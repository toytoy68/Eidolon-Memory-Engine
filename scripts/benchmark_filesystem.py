"""Synthetic local throughput sample; never touches configured memory roots."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter

from core.backend.filesystem import FilesystemBackend
from core.backend.models import Memory
from core.indexing import build_manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Temporary synthetic filesystem benchmark")
    parser.add_argument("--count", type=int, default=1000,
                        help="Number of synthetic Informations (1..100000)")
    args = parser.parse_args(argv)
    if not 1 <= args.count <= 100_000:
        parser.error("count must be between 1 and 100000")
    with TemporaryDirectory(prefix="eidolon-benchmark-") as directory:
        root = Path(directory)
        backend = FilesystemBackend(root / "persistent", root / "history")
        start = perf_counter()
        for number in range(args.count):
            backend.store(Memory(f"item-{number:06d}", content=(
                "synthetic content " * 5 + (" needle" if number == args.count - 1 else ""))))
        stored = perf_counter()
        page = backend.list(limit=100)
        listed = perf_counter()
        matches = backend.search("needle")
        searched = perf_counter()
        ranked_matches = backend.search("needle", {"ranking": "lexical_v1"})
        ranked = perf_counter()
        manifest = build_manifest(backend.persistent_root)
        indexed = perf_counter()
    print(json.dumps({
        "count": args.count, "first_page_count": len(page),
        "search_matches": len(matches), "manifest_count": len(manifest.entries),
        "ranked_search_matches": len(ranked_matches),
        "store_seconds": round(stored - start, 4),
        "first_page_seconds": round(listed - stored, 4),
        "search_seconds": round(searched - listed, 4),
        "ranked_search_seconds": round(ranked - searched, 4),
        "manifest_seconds": round(indexed - ranked, 4),
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
