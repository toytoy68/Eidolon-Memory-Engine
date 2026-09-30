import json
from pathlib import Path

from core.backend.filesystem import FilesystemBackend
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


def test_epistemic_status_does_not_hide_relevant_specific_documents():
    judgments = json.loads((FIXTURES / "scenario-status-judgments.json").read_text())
    baseline = json.loads((FIXTURES / "scenario-status-baseline.json").read_text())
    assert len(judgments["cases"]) == 30
    targets = [next(identity for identity, grade in case["relevance"].items()
                    if grade == 3) for case in judgments["cases"]]
    assert {int(identity.rsplit("-", 1)[1]) // 10 for identity in targets} == {2, 3, 4}
    assert evaluate_judgments(judgments) == baseline
    assert baseline["metrics"]["mrr_at_5"] == 1.0
    assert main(["--judgments", str(FIXTURES / "scenario-status-judgments.json"),
                 "--baseline", str(FIXTURES / "scenario-status-baseline.json"),
                 "--check"]) == 0


def test_status_baseline_detects_implicit_refuted_filter(monkeypatch):
    judgments = json.loads((FIXTURES / "scenario-status-judgments.json").read_text())
    expected = json.loads((FIXTURES / "scenario-status-baseline.json").read_text())
    original = FilesystemBackend.search

    def masked(self, query, options=None):
        return [hit for hit in original(self, query, options)
                if hit.memory.metadata.get("epistemic_status") != "REFUTED"]

    monkeypatch.setattr(FilesystemBackend, "search", masked)

    assert evaluate_judgments(judgments)["metrics"]["mrr_at_5"] < expected["metrics"]["mrr_at_5"]
