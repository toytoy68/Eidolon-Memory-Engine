import json

import pytest

from scripts.evaluate_retrieval import evaluate, main


def sample():
    return {
        "documents": [
            {"information_id": "a-meta", "content": "unrelated",
             "metadata": {"topic": "pompe cuivre", "private": "do not print"}},
            {"information_id": "z-content", "content": "pompe cuivre"},
        ],
        "cases": [{"query": "pompe cuivre", "relevant_ids": ["z-content"]}],
    }


def test_evaluation_compares_rankings_without_exposing_documents(tmp_path, capsys):
    fixture = tmp_path / "judgments.json"
    fixture.write_text(json.dumps(sample()), encoding="utf-8")
    assert main(["--fixture", str(fixture), "--top-k", "1"]) == 0
    output = capsys.readouterr().out
    report = json.loads(output)
    assert report["rankings"]["legacy"]["recall_at_k"] == 0
    assert report["rankings"]["lexical_v1"]["recall_at_k"] == 1
    assert "do not print" not in output
    assert "pompe cuivre" not in output
    assert not list(tmp_path.glob("persistent"))


@pytest.mark.parametrize("invalid", [
    {"documents": [], "cases": []},
    {"documents": [{"information_id": "../escape", "content": "x"}],
     "cases": [{"query": "x", "relevant_ids": ["../escape"]}]},
    {"documents": [{"information_id": "a", "content": "x"}],
     "cases": [{"query": "x", "relevant_ids": ["missing"]}]},
])
def test_evaluation_rejects_invalid_judgments(invalid):
    with pytest.raises(ValueError):
        evaluate(invalid)


def test_evaluation_rejects_duplicate_json_keys(tmp_path):
    fixture = tmp_path / "ambiguous.json"
    fixture.write_text('{"documents": [], "documents": [], "cases": []}')
    with pytest.raises(SystemExit) as exc:
        main(["--fixture", str(fixture)])
    assert exc.value.code == 2
