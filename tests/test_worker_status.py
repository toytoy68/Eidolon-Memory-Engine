from core.indexing.worker_prepare import PreparedWork
from core.indexing.worker_status import summarize_work
import pytest


def test_index_current_only_when_no_pending_or_review():
    result = summarize_work(PreparedWork((), (), ()), index_available=True,
                            canonical_complete=True, model_compatible=True)
    assert result.state == "INDEX_CURRENT"


@pytest.mark.parametrize("flags,expected", [
    ((False, True, True), "INDEX_UNAVAILABLE"),
    ((True, True, False), "INDEX_INCOMPATIBLE"),
    ((True, False, True), "INDEX_STALE"),
])
def test_unhealthy_index_states_take_priority(flags, expected):
    result = summarize_work(PreparedWork(("doc",), (), ()), index_available=flags[0],
                            canonical_complete=flags[1], model_compatible=flags[2])
    assert result.state == expected


def test_pending_is_not_review():
    result = summarize_work(PreparedWork((), (), (), ("doc",)),
                            index_available=True, canonical_complete=True, model_compatible=True)
    assert result.state == "INDEX_PENDING"
    assert result.review == 0


def test_human_review_is_distinct_from_pending():
    result = summarize_work(PreparedWork((), ("doc",), (), ("other",)),
                            index_available=True, canonical_complete=True, model_compatible=True)
    assert result.state == "REVIEW_REQUIRED"
    assert result.waiting == 1


def test_invalid_flags_fail_closed():
    with pytest.raises(ValueError):
        summarize_work(PreparedWork((), (), ()), index_available=1,
                       canonical_complete=True, model_compatible=True)

def test_blocked_work_is_not_reported_current():
    result = summarize_work(PreparedWork((), (), ("doc",)),
                            index_available=True, canonical_complete=True, model_compatible=True)
    assert result.state == "POLICY_BLOCKED"

def test_status_rejects_empty_document_identifier():
    with pytest.raises(ValueError, match="entries"):
        summarize_work(PreparedWork(("",), (), ()), index_available=True,
                       canonical_complete=True, model_compatible=True)


def test_multiple_pending_intents_same_document_are_allowed():
    result = summarize_work(PreparedWork(("doc", "doc"), (), ()),
                            index_available=True, canonical_complete=True, model_compatible=True)
    assert result.state == "INDEX_PENDING"
    assert result.candidates == 2
