"""Evaluate filesystem retrieval on explicit, synthetic or anonymized judgments."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from tempfile import TemporaryDirectory

from core.backend.filesystem import FilesystemBackend
from core.backend.models import Memory


def _validate_fixture(data: object) -> tuple[list[dict], list[dict]]:
    if not isinstance(data, dict) or set(data) != {"documents", "cases"}:
        raise ValueError("fixture must contain documents and cases")
    documents, cases = data["documents"], data["cases"]
    if not isinstance(documents, list) or not documents or not isinstance(cases, list) or not cases:
        raise ValueError("fixture needs nonempty documents and cases")
    seen = set()
    for document in documents:
        if (not isinstance(document, dict) or set(document) -
                {"information_id", "content", "metadata", "provenance", "temporal",
                 "verification", "relations"} or
                not isinstance(document.get("information_id"), str) or
                not re.fullmatch(r"[A-Za-z0-9._-]+", document["information_id"]) or
                not isinstance(document.get("content"), str) or
                any(not isinstance(document.get(field, {}), dict)
                    for field in ("metadata", "provenance", "temporal", "verification")) or
                not isinstance(document.get("relations", []), list)):
            raise ValueError("invalid evaluation document")
        identifier = document["information_id"]
        if identifier in seen:
            raise ValueError("duplicate evaluation document")
        seen.add(identifier)
    for case in cases:
        if (not isinstance(case, dict) or set(case) != {"query", "relevant_ids"}
                or not isinstance(case["query"], str) or not case["query"].strip()
                or not isinstance(case["relevant_ids"], list)
                or not case["relevant_ids"] or
                any(type(identifier) is not str or identifier not in seen
                    for identifier in case["relevant_ids"])
                or len(set(case["relevant_ids"])) != len(case["relevant_ids"])):
            raise ValueError("invalid evaluation judgment")
    return documents, cases


def _metrics(ranked_ids: list[str], relevant: set[str], top_k: int) -> tuple[float, float, float]:
    selected = ranked_ids[:top_k]
    hits = len(relevant.intersection(selected))
    first_rank = next((index for index, identifier in enumerate(selected, 1)
                       if identifier in relevant), None)
    return hits / top_k, hits / len(relevant), 1 / first_rank if first_rank else 0.0


def evaluate(data: object, *, top_k: int = 5) -> dict:
    if type(top_k) is not int or top_k < 1:
        raise ValueError("top_k must be positive")
    documents, cases = _validate_fixture(data)
    with TemporaryDirectory(prefix="eidolon-retrieval-evaluation-") as directory:
        root = Path(directory)
        backend = FilesystemBackend(root / "persistent", root / "history")
        for document in documents:
            backend.store(Memory(**document))
        results = {}
        for ranking in ("legacy", "lexical_v1"):
            totals = [0.0, 0.0, 0.0]
            for case in cases:
                ranked_ids = [hit.memory.information_id for hit in backend.search(
                    case["query"], {"ranking": ranking, "limit": len(documents)})]
                measures = _metrics(ranked_ids, set(case["relevant_ids"]), top_k)
                for index, value in enumerate(measures):
                    totals[index] += value
            results[ranking] = {
                "precision_at_k": round(totals[0] / len(cases), 4),
                "recall_at_k": round(totals[1] / len(cases), 4),
                "mrr_at_k": round(totals[2] / len(cases), 4),
            }
    return {"documents": len(documents), "cases": len(cases), "top_k": top_k,
            "rankings": results}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Evaluate retrieval on a judged fixture")
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--top-k", type=int, default=5)
    args = parser.parse_args(argv)
    try:
        def unique_object(pairs):
            result = {}
            for key, value in pairs:
                if key in result:
                    raise ValueError("duplicate fixture key")
                result[key] = value
            return result

        def invalid_constant(value):
            raise ValueError("invalid fixture constant")

        data = json.loads(args.fixture.read_text(encoding="utf-8"),
                          object_pairs_hook=unique_object,
                          parse_constant=invalid_constant)
        report = evaluate(data, top_k=args.top_k)
    except (OSError, UnicodeError, ValueError, TypeError) as exc:
        parser.error(str(exc))
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
