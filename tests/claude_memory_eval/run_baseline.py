# ==========================================================
# Projet      : Eidolon Memory Engine
# Organisation: Eidolon Core Technologies (ECT)
# Fichier     : tests/claude_memory_eval/run_baseline.py
# Description : Baseline de rappel sur le corpus synthétique : rappel@k, sources, abstention, latence (G178)
# Standard    : Eidolon Presentation Standard v1
# ==========================================================
"""From the repository root:

  python3 tests/claude_memory_eval/run_baseline.py [--out docs/claude-memory-eval/baseline-lexical-v1.json]

RETRIEVAL ONLY (no generation, no model). Every document is stored as a one-message conversation archive in a
temporary FilesystemBackend, then ContextualRecall answers each question with its defaults (max_items=5).
The references in corpus-v1.json were fixed before any run; this script never reads results back into them.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import statistics
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from core.backend.filesystem import FilesystemBackend          # noqa: E402
from core.backend.models import Memory                         # noqa: E402
from core.retrieval.contextual import ContextualRecall         # noqa: E402

CORPUS = ROOT / "docs" / "claude-memory-eval" / "corpus-v1.json"


def build(root, documents):
    backend = FilesystemBackend(root / "memory/persistent", root / "memory/history")
    for document in documents:
        created = int(datetime.fromisoformat(document["date"]).replace(tzinfo=timezone.utc).timestamp())
        message = {"content": document["text"], "node_id": "m", "message_id": "m", "parent": None,
                   "role": "user", "created_at": created}
        backend.store(Memory(document["id"], content=json.dumps({"conversation_id": document["id"], "messages": [message]},
                                                                ensure_ascii=False),
                             metadata={"archive_kind": "conversation", "epistemic_status": "UNVERIFIED"},
                             provenance={"importer": "chatgpt-archive-v1", "conversation_id": document["id"]}))
    return backend


def evaluate(corpus, recall, k_values=(1, 3, 5)):
    rows = []
    for question in corpus["questions"]:
        started = time.perf_counter()
        items = recall(question["question"])
        latency_ms = (time.perf_counter() - started) * 1000
        ids = [item.information_id for item in items]
        expected = question["expected"]
        row = {"id": question["id"], "category": question["category"], "returned": ids,
               "latency_ms": round(latency_ms, 2)}
        if expected:
            rank = next((ids.index(e) + 1 for e in expected if e in ids), None)
            row["rank"] = rank
            row.update({f"hit@{k}": rank is not None and rank <= k for k in k_values})
            check = question.get("check") or {}
            if "excerpt_contains" in check:
                excerpt = next((item.content for item in items if item.information_id in expected), "")
                row["check_ok"] = check["excerpt_contains"].casefold() in excerpt.casefold()
            if "before" in check:
                other = check["before"]
                row["check_ok"] = rank is not None and (other not in ids or ids.index(other) + 1 > rank)
            if "not_top" in check:
                row["check_ok"] = not ids or ids[0] != check["not_top"]
        else:
            row["abstained"] = not ids
        rows.append(row)
    return rows


def summarize(rows, k_values=(1, 3, 5)):
    answerable = [r for r in rows if "rank" in r]
    absent = [r for r in rows if "abstained" in r]
    checks = [r for r in rows if "check_ok" in r]
    out = {f"recall@{k}": round(sum(r[f"hit@{k}"] for r in answerable) / len(answerable), 3) for k in k_values}
    out.update(answerable=len(answerable), abstention_rate=round(sum(r["abstained"] for r in absent) / len(absent), 3),
               absence_questions=len(absent), checks_passed=f"{sum(r['check_ok'] for r in checks)}/{len(checks)}",
               latency_ms_median=round(statistics.median(r["latency_ms"] for r in rows), 2),
               latency_ms_max=round(max(r["latency_ms"] for r in rows), 2))
    categories = {}
    for row in rows:
        c = categories.setdefault(row["category"], {"n": 0, "hit@1": 0, "hit@5": 0, "checks": [0, 0], "abstained": 0})
        c["n"] += 1
        c["hit@1"] += row.get("hit@1", False)
        c["hit@5"] += row.get("hit@5", False)
        c["abstained"] += row.get("abstained", False)
        if "check_ok" in row:
            c["checks"][0] += row["check_ok"]; c["checks"][1] += 1
    out["by_category"] = {name: {**v, "checks": f"{v['checks'][0]}/{v['checks'][1]}"} for name, v in sorted(categories.items())}
    return out


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=str(ROOT / "docs" / "claude-memory-eval" / "baseline-lexical-v1.json"))
    args = parser.parse_args()
    raw = CORPUS.read_bytes()
    corpus = json.loads(raw)
    with tempfile.TemporaryDirectory(prefix="eidolon-eval-") as tmp:
        recall_engine = ContextualRecall(build(Path(tmp), corpus["documents"]))
        rows = evaluate(corpus, lambda question: recall_engine.recall(question).items)
    result = {"schema": "claude-memory-eval-result/1", "engine": "ContextualRecall defaults (lexical_passage_v1, passage v3)",
              "corpus_sha256": hashlib.sha256(raw).hexdigest(), "retrieval_only": True, "synthetic": True,
              "summary": summarize(rows), "rows": rows}
    Path(args.out).write_text(json.dumps(result, ensure_ascii=False, indent=1) + "\n")
    print(json.dumps(result["summary"], ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
