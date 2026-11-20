# ==========================================================
# Projet      : Eidolon Memory Engine
# Organisation: Eidolon Core Technologies (ECT)
# Fichier     : tools/evaluation/score_long_corpus.py
# Description : Offline retrieval scoring, separated from index inputs
# Standard    : Eidolon Presentation Standard v1
# ==========================================================
"""Score document retrieval only. Never interpret a candidate as a supported answer."""
import argparse
import json
from pathlib import Path
import statistics


def read(path):
    return [json.loads(x) for x in path.read_text().splitlines() if x]


def score(run, oracle):
    answers = read(oracle)
    summary = json.loads((run / "summary.json").read_text())
    if (not summary.get("completed") or len(answers) != 1000
            or [a["id"] for a in answers] != [f"Q-{i:04d}" for i in range(1, 1001)]
            or any(a["status"] not in {"answerable", "not_in_corpus"} for a in answers)):
        raise ValueError("incomplete run/oracle")
    result = {"scope": "retrieval of evidence documents; no generated answers scored",
              "measurements": [], "ranking_parity": {}}
    for size in (10, 50, 100):
        expected = {r["id"]: r for r in answers[:size * 10]}
        identities = {f"DOC-{i:03d}" for i in range(1, size + 1)}
        ranks = {}
        for adapter in ("reference", "fts5_verified"):
            rows = read(run / str(size) / f"{adapter}-retrieval.jsonl")
            if len(rows) != size * 10 or {r["id"] for r in rows} != set(expected):
                raise ValueError("missing or duplicate query results")
            groups, unknown, ranks[adapter] = {}, [], {}
            for row in rows:
                hits = [h["id"] for h in row["hits"]]
                if len(hits) > 5 or len(hits) != len(set(hits)) or not set(hits) <= identities:
                    raise ValueError("invalid retrieved identities")
                ranks[adapter][row["id"]] = hits
                truth = expected[row["id"]]
                if truth["status"] != "answerable":
                    unknown.append(bool(hits))
                    continue
                relevant = set(truth["evidence_documents"])
                if not relevant or not relevant <= identities:
                    raise ValueError("oracle refers outside the batch")
                metrics = {"recall_at_1": len(relevant & set(hits[:1])) / len(relevant),
                           "recall_at_5": len(relevant & set(hits)) / len(relevant),
                           "all_evidence_at_5": int(relevant <= set(hits)),
                           "reciprocal_rank": next((1 / rank for rank, x in enumerate(hits, 1)
                                                    if x in relevant), 0)}
                for name in ("all_answerable", row["type"]):
                    groups.setdefault(name, []).append(metrics)
            aggregate = {name: {"queries": len(items), **{
                k: statistics.mean(x[k] for x in items) for k in items[0]}}
                for name, items in groups.items()}
            result["measurements"].append({"documents": size, "adapter": adapter,
                "quality": aggregate, "unknown_queries": len(unknown),
                "unknown_with_candidates": sum(unknown),
                "unknown_note": "Candidate presence does not measure false answers or abstention."})
        result["ranking_parity"][str(size)] = {
            "queries": size * 10,
            "different_ordered_top5": sum(ranks["reference"][q] != ranks["fts5_verified"][q]
                                        for q in expected)}
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--oracle", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(score(args.run, args.oracle), indent=2, ensure_ascii=False))
