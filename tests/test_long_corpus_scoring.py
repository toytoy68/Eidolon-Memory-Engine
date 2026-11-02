"""Prevent inflated FR100 metrics from missing evidence or negative controls."""
import json

import pytest

from tools.evaluation.score_long_corpus import score


@pytest.fixture
def fixture_run(tmp_path):
    oracle = tmp_path / "answers.jsonl"
    answers = [{"id": f"Q-{i:04d}", "status": "answerable",
                "evidence_documents": ["DOC-001", "DOC-002"]}
               for i in range(1, 1001)]
    # Negative controls retain origin evidence in FR100; this is not a positive label.
    answers[0]["status"] = "not_in_corpus"
    oracle.write_text("\n".join(map(json.dumps, answers)))
    (tmp_path / "summary.json").write_text('{"completed": true}')
    for size in (10, 50, 100):
        directory = tmp_path / str(size)
        directory.mkdir()
        rows = [{"id": f"Q-{i:04d}", "type": "cross_document",
                 "hits": [{"id": "DOC-003"}, {"id": "DOC-001"}]}
                for i in range(1, size * 10 + 1)]
        for name in ("reference", "fts5_verified"):
            (directory / f"{name}-retrieval.jsonl").write_text("\n".join(map(json.dumps, rows)))
    return tmp_path, oracle


def test_partial_evidence_and_unknowns_are_not_full_success(fixture_run):
    result = score(*fixture_run)
    for row in result["measurements"]:
        metrics = row["quality"]["all_answerable"]
        assert metrics == {"queries": row["documents"] * 10 - 1,
                           "recall_at_1": 0, "recall_at_5": .5,
                           "all_evidence_at_5": 0, "reciprocal_rank": .5}
        assert row["unknown_queries"] == row["unknown_with_candidates"] == 1
    assert all(x["different_ordered_top5"] == 0 for x in result["ranking_parity"].values())


@pytest.mark.parametrize("damage", ["missing", "duplicate", "outside_batch", "duplicate_hit"])
def test_invalid_retrieval_cannot_silently_improve_metrics(fixture_run, damage):
    directory, oracle = fixture_run
    path = directory / "10/reference-retrieval.jsonl"
    rows = [json.loads(x) for x in path.read_text().splitlines()]
    if damage == "missing":
        rows.pop()
    elif damage == "duplicate":
        rows[-1] = rows[0]
    elif damage == "outside_batch":
        rows[0]["hits"] = [{"id": "DOC-011"}]
    else:
        rows[0]["hits"] *= 2
    path.write_text("\n".join(map(json.dumps, rows)))
    with pytest.raises(ValueError):
        score(directory, oracle)


def test_unknown_oracle_status_is_rejected(fixture_run):
    directory, oracle = fixture_run
    oracle.write_text(oracle.read_text().replace('"not_in_corpus"', '"unsupported_typo"', 1))
    with pytest.raises(ValueError):
        score(directory, oracle)
