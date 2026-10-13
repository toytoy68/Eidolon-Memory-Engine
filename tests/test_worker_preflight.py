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
    assert len(result.proposals) == 3
    assert [a.kind for a in result.review] == ["ENQUEUE_DELETE"]


def test_unknown_action_is_rejected():
    with pytest.raises(ValueError, match="unknown"):
        preflight([action("EXECUTE_DELETE")])


def test_invalid_policy_is_rejected():
    with pytest.raises(ValueError, match="policy"):
        preflight([], allow_upsert=1)
