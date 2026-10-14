# ==========================================================
# Projet      : Eidolon Memory Engine
# Organisation: Eidolon Core Technologies (ECT)
# Fichier     : tests/test_reconcile_integrity.py
# Description : Detect same-revision drift without trusting revision alone.
# Standard    : Eidolon Presentation Standard v1
# ==========================================================
from core.indexing.port import IndexEvidence
from core.indexing.reconcile_plan import Canonical, reconcile_plan
from core.indexing.reconcile_preview import preview_reconciliation
from core.indexing.change_journal import ChangeJournal
from dataclasses import replace
import pytest


def test_same_revision_digest_drift_requires_review():
    actions = reconcile_plan(
        (), {"doc": Canonical(1, "a" * 64)}, {"doc": 1},
        indexed_evidence={"doc": IndexEvidence("doc", 1, "b" * 64, "model", "gen")},
        expected_embedding_id="model", expected_generation="gen")
    assert [a.kind for a in actions] == ["INTEGRITY_ALERT"]


@pytest.mark.parametrize("field,value", [("embedding_id", "other"), ("generation", "other")])
def test_model_and_generation_drift_require_review(field, value):
    point = replace(IndexEvidence("doc", 1, "a" * 64, "model", "gen"), **{field: value})
    actions = reconcile_plan((), {"doc": Canonical(1, "a" * 64)}, {"doc": 1},
                             indexed_evidence={"doc": point},
                             expected_embedding_id="model", expected_generation="gen")
    assert [a.kind for a in actions] == ["INTEGRITY_ALERT"]


def test_missing_proof_requires_upsert_even_at_same_revision():
    actions = reconcile_plan((), {"doc": Canonical(1, "a" * 64)}, {"doc": 1},
                             indexed_evidence={}, expected_embedding_id="model", expected_generation="gen")
    assert [a.kind for a in actions] == ["ENQUEUE_UPSERT"]


def test_matching_proof_is_noop_and_older_revision_proposes_update():
    point = IndexEvidence("doc", 1, "a" * 64, "model", "gen")
    for revision, expected in [(1, []), (2, ["ENQUEUE_UPSERT"])]:
        actions = reconcile_plan((), {"doc": Canonical(revision, "a" * 64)}, {"doc": 1},
                                 indexed_evidence={"doc": point},
                                 expected_embedding_id="model", expected_generation="gen")
        assert [a.kind for a in actions] == expected


@pytest.mark.parametrize("field,value", [("revision", True), ("canonical_sha256", "bad"),
                                         ("information_id", "other"), ("generation", "")])
def test_malformed_proof_is_refused(field, value):
    point = replace(IndexEvidence("doc", 1, "a" * 64, "model", "gen"), **{field: value})
    with pytest.raises(ValueError, match="evidence"):
        reconcile_plan((), {"doc": Canonical(1, "a" * 64)}, {"doc": 1},
                       indexed_evidence={"doc": point},
                       expected_embedding_id="model", expected_generation="gen")


@pytest.mark.parametrize("pending", [False, True])
def test_preview_marks_digest_alert_for_review_even_with_pending_intent(tmp_path, pending):
    journal = ChangeJournal(tmp_path / "changes.sqlite3")
    if pending:
        seq = journal.begin("doc", 1, "UPSERT", "a" * 64)
        journal.published(seq)
    preview = preview_reconciliation(
        journal, {"doc": Canonical(1, "a" * 64)}, {"doc": 1},
        indexed_evidence={"doc": IndexEvidence("doc", 1, "b" * 64, "model", "gen")},
        expected_embedding_id="model", expected_generation="gen")
    assert preview.requires_review
    assert [a.kind for a in preview.actions] == ["INTEGRITY_ALERT"]


def test_context_cannot_silently_fall_back_to_revision_only():
    with pytest.raises(ValueError, match="evidence"):
        reconcile_plan((), {}, {}, expected_embedding_id="model")
    with pytest.raises(ValueError, match="context"):
        reconcile_plan((), {}, {}, indexed_evidence={})
