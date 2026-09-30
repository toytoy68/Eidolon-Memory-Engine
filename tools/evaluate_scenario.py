"""Measure lexical_v1 on 30 versioned partial relevance judgments."""

from __future__ import annotations

import argparse
from hashlib import sha256
import json
from math import log2
from pathlib import Path
from tempfile import TemporaryDirectory

from core.backend.filesystem import FilesystemBackend
from tools.generate_scenario import generate


FIXTURES = Path(__file__).resolve().parents[1] / "tests/fixtures"


def evaluate_judgments(judgments: dict) -> dict:
    with TemporaryDirectory(prefix="eidolon-scenario-") as directory:
        root = Path(directory) / "scenario"
        generated = generate(root, seed=judgments["seed"], count=judgments["count"])
        backend = FilesystemBackend(root / "core/memory/persistent", root / "core/memory/history")
        totals = {"recall_at_5": 0.0, "mrr_at_5": 0.0, "ndcg_at_5": 0.0}
        for case in judgments["cases"]:
            relevant = case["relevance"]
            hits = [result.memory.information_id for result in backend.search(
                case["query"], {"ranking": "lexical_v1", "limit": 5})]
            totals["recall_at_5"] += len(set(hits) & set(relevant)) / len(relevant)
            first = next((rank for rank, identity in enumerate(hits, 1)
                          if identity in relevant), None)
            totals["mrr_at_5"] += 1 / first if first else 0.0
            dcg = sum((2 ** relevant.get(identity, 0) - 1) / log2(rank + 1)
                      for rank, identity in enumerate(hits, 1))
            ideal = sum((2 ** grade - 1) / log2(rank + 1)
                        for rank, grade in enumerate(sorted(relevant.values(), reverse=True)[:5], 1))
            totals["ndcg_at_5"] += dcg / ideal if ideal else 0.0
        return {"ranking": "lexical_v1", "documents": generated["information"],
                "cases": len(judgments["cases"]), "judgments": "partial_synthetic",
                "judgments_sha256": sha256(json.dumps(judgments, ensure_ascii=False,
                                                    sort_keys=True).encode()).hexdigest(),
                "metrics": {name: round(value / len(judgments["cases"]), 4)
                            for name, value in totals.items()}}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--judgments", type=Path, default=FIXTURES / "scenario-judgments.json")
    parser.add_argument("--baseline", type=Path, default=FIXTURES / "scenario-baseline.json")
    action = parser.add_mutually_exclusive_group()
    action.add_argument("--check", action="store_true", help="Compare against versioned baseline")
    action.add_argument("--write-baseline", action="store_true", help="Explicitly replace baseline")
    args = parser.parse_args(argv)
    result = evaluate_judgments(json.loads(args.judgments.read_text(encoding="utf-8")))
    if args.write_baseline:
        args.baseline.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if args.check and result != json.loads(args.baseline.read_text(encoding="utf-8")):
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
