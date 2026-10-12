# ==========================================================
# Projet      : Eidolon Memory Engine
# Organisation: Eidolon Core Technologies (ECT)
# Fichier     : tests/claude_memory_eval/test_corpus_and_runner.py
# Description : Intégrité du corpus synthétique et exécution du banc ; aucune valeur de score imposée au moteur (G178)
# Standard    : Eidolon Presentation Standard v1
# ==========================================================
"""These tests guard the corpus and the runner, NOT the engine's quality: results are measured and published
(docs/claude-memory-eval/), never asserted here, so a better engine never has to edit expectations."""
import hashlib
import json
from pathlib import Path

from tests.claude_memory_eval.run_baseline import CORPUS, build, evaluate, summarize
from core.retrieval.contextual import ContextualRecall

FROZEN_SHA256 = "80ea76bf9054834ae6d8e73ba36df38c38c7d0fd4148eb727a3ae3e9bb82a3a1"
CATEGORIES = {"paraphrase", "direct", "negation", "corrected", "tech_vs_fiction", "homonym", "condition", "absence"}


def corpus():
    return json.loads(CORPUS.read_text())


def test_corpus_is_frozen_unless_its_version_changes():
    # Editing references after seeing results is forbidden: a new corpus needs a new file and version.
    assert hashlib.sha256(CORPUS.read_bytes()).hexdigest() == FROZEN_SHA256


def test_references_point_to_existing_documents_and_categories_are_known():
    value = corpus()
    ids = [d["id"] for d in value["documents"]]
    assert len(ids) == len(set(ids)) and value["synthetic"] is True
    for question in value["questions"]:
        assert question["category"] in CATEGORIES
        assert all(e in ids for e in question["expected"])
        assert (question["category"] == "absence") == (not question["expected"])
        for key, target in (question.get("check") or {}).items():
            assert key in {"excerpt_contains", "before", "not_top"}
            if key != "excerpt_contains":
                assert target in ids


def test_runner_measures_every_question_without_judging_scores(tmp_path):
    value = corpus()
    engine = ContextualRecall(build(tmp_path, value["documents"]))
    rows = evaluate(value, lambda q: engine.recall(q).items)
    summary = summarize(rows)
    assert len(rows) == len(value["questions"])
    assert all(0 <= summary[k] <= 1 for k in ("recall@1", "recall@3", "recall@5", "abstention_rate"))
    assert set(summary["by_category"]) == CATEGORIES
