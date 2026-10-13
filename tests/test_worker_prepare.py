from core.indexing.reconcile_plan import Action
from core.indexing.reconcile_preview import ReconcilePreview
from core.indexing.worker_prepare import prepare_work
import pytest


def preview(kinds, review=False):
    actions = tuple(Action(k, f"doc-{i}", i + 1, 1, "test") for i, k in enumerate(kinds))
    return ReconcilePreview(actions, len(actions), 0.0, review)


def test_default_worker_preparation_has_no_candidates():
    result = prepare_work(preview(["INDEX_UPSERT"]))
    assert result.candidate_ids == ()
    assert result.blocked_ids == ("doc-0",)


def test_explicit_upsert_is_only_a_candidate():
    result = prepare_work(preview(["INDEX_UPSERT", "ENQUEUE_DELETE"]), allow_upsert=True)
    assert result.candidate_ids == ("doc-0",)
    assert result.review_ids == ("doc-1",)


def test_review_required_blocks_all_candidates():
    result = prepare_work(preview(["INDEX_UPSERT", "INTEGRITY_ALERT"], review=True), allow_upsert=True)
    assert result.candidate_ids == ()
    assert "doc-0" in result.review_ids


def test_invalid_preview_is_rejected():
    with pytest.raises(ValueError):
        prepare_work(None)

def test_waiting_is_reported_without_human_review():
    result = prepare_work(preview(["WAIT"]), allow_upsert=True)
    assert result.candidate_ids == ()
    assert result.review_ids == ()
    assert result.waiting_ids == ("doc-0",)
