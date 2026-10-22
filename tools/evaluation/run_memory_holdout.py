"""Read-only Memory holdout (Claude, G294): near-negatives and keywordless paraphrases.

For a near-negative, ``trap_id`` names the related note that does NOT answer. Its rank
measures how often Core receives plausible but insufficient evidence; it is never an
expected answer. Same local endpoint and limits as run_memory_50. No writes.
"""
import argparse
import json
from pathlib import Path
from statistics import median
from time import monotonic
from urllib.request import Request, urlopen

KINDS = {"near_negative", "paraphrase_no_keyword"}


def validate(payload):
    if payload.get("schema") != "eidolon-memory-holdout/1":
        raise ValueError("unknown holdout schema")
    cases = payload.get("cases")
    if not isinstance(cases, list) or not 1 <= len(cases) <= 200 or len({c["id"] for c in cases}) != len(cases):
        raise ValueError("invalid or duplicate cases")
    for c in cases:
        if c.get("kind") not in KINDS or not isinstance(c.get("query"), str) or not 1 <= len(c["query"]) <= 500:
            raise ValueError("invalid case")
        if (c["kind"] == "near_negative") != (c.get("expected_id") is None):
            raise ValueError("near-negatives alone have no expected answer")
        target = c.get("expected_id") or c.get("trap_id")
        if not isinstance(target, str) or not target:
            raise ValueError("expected_id or trap_id required")
    return cases


def summarize(rows):
    out = {}
    for kind in sorted(KINDS):
        sub = [r for r in rows if r["kind"] == kind and "error" not in r]
        scores = [r["first_score"] for r in sub if r["first_score"] is not None]
        out[kind] = {"cases": len(sub), "target_top1": sum(r["target_rank"] == 1 for r in sub),
                     "target_top5": sum(r["target_rank"] is not None for r in sub),
                     "with_candidates": sum(r["candidates"] > 0 for r in sub),
                     "first_score_min": min(scores) if scores else None,
                     "first_score_max": max(scores) if scores else None}
    out["errors"] = sum("error" in r for r in rows)
    out["median_ms"] = median(r["duration_ms"] for r in rows) if rows else None
    out["score_is_proof"] = False
    out["threshold_calibrated"] = False
    return out


def run(cases, *, url, token, timeout):
    rows = []
    for c in cases:
        start = monotonic()
        body = json.dumps({"query": c["query"], "mode": "operational", "max_items": 5,
                           "max_chars": 4000, "max_item_chars": 800}).encode()
        try:
            with urlopen(Request(url, data=body, headers={"Authorization": "Bearer " + token,
                                                           "Content-Type": "application/json"}), timeout=timeout) as r:
                data = json.load(r)
            if data.get("schema") != "eidolon-memory-recall/1":
                raise ValueError("wrong response schema")
            items = data["result"]["items"]
            ids = [i["information_id"] for i in items]
            target = c.get("expected_id") or c["trap_id"]
            row = {"id": c["id"], "kind": c["kind"], "candidates": len(ids),
                   "target_rank": ids.index(target) + 1 if target in ids else None,
                   "first_score": items[0].get("score") if items else None}
        except Exception as exc:
            row = {"id": c["id"], "kind": c["kind"], "error": type(exc).__name__}
        row["duration_ms"] = round((monotonic() - start) * 1000, 1)
        rows.append(row)
        print(json.dumps(row, ensure_ascii=False), flush=True)
    return {"schema": "eidolon-memory-holdout-report/1", "summary": summarize(rows), "rows": rows}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fixture", required=True, type=Path)
    ap.add_argument("--env-file", required=True, type=Path)
    ap.add_argument("--output", required=True, type=Path)
    ap.add_argument("--url", default="http://127.0.0.1:18765/v1/recall")
    ap.add_argument("--timeout", type=float, default=20)
    args = ap.parse_args()
    if args.url != "http://127.0.0.1:18765/v1/recall":
        ap.error("only local read-only recall endpoint permitted")
    cases = validate(json.loads(args.fixture.read_text()))
    values = dict(line.split("=", 1) for line in args.env_file.read_text().splitlines() if "=" in line)
    report = run(cases, url=args.url, token=values["EIDOLON_MEMORY_BRIDGE_TOKEN"].strip().strip("\"'"),
                 timeout=args.timeout)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print("SUMMARY", json.dumps(report["summary"]), flush=True)
    if report["summary"]["errors"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
