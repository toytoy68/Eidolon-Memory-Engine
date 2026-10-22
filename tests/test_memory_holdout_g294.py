import json
from pathlib import Path
import pytest
from tools.evaluation.run_memory_holdout import validate, summarize

FIXTURE = Path(__file__).parent / "evaluation/memory-holdout-g294.json"


def test_fixture_is_valid_and_separates_traps_from_answers():
    cases = validate(json.loads(FIXTURE.read_text()))
    assert sum(c["kind"] == "near_negative" for c in cases) == 12
    assert sum(c["kind"] == "paraphrase_no_keyword" for c in cases) == 8
    assert all(c["expected_id"] is None and c["trap_id"] for c in cases if c["kind"] == "near_negative")


@pytest.mark.parametrize("mutation", ["expected", "duplicate", "kind", "target"])
def test_invalid_holdouts_are_refused(mutation):
    data = json.loads(FIXTURE.read_text())
    if mutation == "expected":
        data["cases"][0]["expected_id"] = data["cases"][0]["trap_id"]
    elif mutation == "duplicate":
        data["cases"][1]["id"] = data["cases"][0]["id"]
    elif mutation == "kind":
        data["cases"][0]["kind"] = "unknown"
    else:
        data["cases"][-1]["expected_id"] = None
    with pytest.raises(ValueError):
        validate(data)


def test_summary_never_claims_proof():
    rows = [{"kind": "near_negative", "candidates": 5, "target_rank": 1, "first_score": .5, "duration_ms": 1},
            {"kind": "paraphrase_no_keyword", "candidates": 5, "target_rank": None, "first_score": .2, "duration_ms": 3}]
    s = summarize(rows)
    assert s["near_negative"]["target_top1"] == 1 and s["paraphrase_no_keyword"]["target_top5"] == 0
    assert s["score_is_proof"] is False and s["threshold_calibrated"] is False
