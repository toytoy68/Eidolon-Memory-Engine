import json
from pathlib import Path

from tools.evaluate_scenario import evaluate_judgments, main


FIXTURES = Path(__file__).parent / "fixtures"


def test_30_judgments_match_versioned_lexical_baseline():
    judgments = json.loads((FIXTURES / "scenario-judgments.json").read_text())
    baseline = json.loads((FIXTURES / "scenario-baseline.json").read_text())
    assert len(judgments["cases"]) == 30
    assert all(set(case["relevance"].values()) <= {1, 2, 3}
               for case in judgments["cases"])
    assert evaluate_judgments(judgments) == baseline
    assert main(["--judgments", str(FIXTURES / "scenario-judgments.json"),
                 "--baseline", str(FIXTURES / "scenario-baseline.json"),
                 "--check"]) == 0
