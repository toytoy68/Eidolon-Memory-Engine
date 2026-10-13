from core.indexing.reconcile_plan import Action
from core.indexing.worker_preflight import preflight
import pytest


def action(kind):
    return Action(kind, "doc", 1, 1, "test")


def test_default_denies_all_executable_actions():
    result = preflight([action("INDEX_UPSERT"), action("INDEX_DELETE")])
    assert result.proposals == ()
    assert len(result.refused) == 1
    assert len(result.review) == 1


def test_upsert_only_when_explicitly_enabled():
    result = preflight([action("INDEX_UPSERT"), action("ENQUEUE_UPSERT"),
                        action("MARK_PUBLISHED"), action("ENQUEUE_DELETE")],
                       allow_upsert=True)
    assert len(result.proposals) == 2
    assert "MARK_PUBLISHED" in [a.kind for a in result.review]
    assert [a.kind for a in result.review] == ["ENQUEUE_DELETE"]


def test_unknown_action_is_rejected():
    with pytest.raises(ValueError, match="unknown"):
        preflight([action("EXECUTE_DELETE")])


def test_invalid_policy_is_rejected():
    with pytest.raises(ValueError, match="policy"):
        preflight([], allow_upsert=1)

def test_publication_is_not_executable_even_with_upsert_enabled():
    result = preflight([action("MARK_PUBLISHED")], allow_upsert=True)
    assert result.proposals == ()
    assert [a.kind for a in result.review] == ["MARK_PUBLISHED"]

def test_wait_is_not_a_human_review_or_executable():
    result = preflight([action("WAIT")], allow_upsert=True)
    assert result.proposals == ()
    assert result.review == ()
    assert [a.kind for a in result.waiting] == ["WAIT"]

def test_duck_typed_action_is_rejected():
    class Forged:
        kind = "INDEX_UPSERT"
        information_id = "doc"
    with pytest.raises(ValueError, match="invalid"):
        preflight([Forged()], allow_upsert=True)


def test_empty_action_identity_is_rejected():
    with pytest.raises(ValueError, match="invalid"):
        preflight([Action("INDEX_UPSERT", "", 1, 1, "bad")], allow_upsert=True)
