from dataclasses import replace
import pytest
from core.threads.models import Thread, ThreadStatus, ThreadAction
from core.threads.queries import ThreadQuery, ThreadQueryType, ThreadSortField, ThreadSortOrder
from core.threads.manager import ThreadManager


def threads():
    return [Thread("open", "Open", "Objective", actions=[ThreadAction("a", "Action")]),
            Thread("done", "Done", "Objective", status=ThreadStatus.COMPLETED,
                   actions=[ThreadAction("b", "Action")]),
            Thread("cancelled", "Cancelled", "Objective", status=ThreadStatus.CANCELLED,
                   actions=[ThreadAction("c", "Action")])]


@pytest.mark.parametrize("kind", [ThreadQueryType.LIST_OPEN_THREADS, ThreadQueryType.LIST_OPEN_ACTIONS])
@pytest.mark.parametrize("completed,cancelled,count", [(False,False,1),(True,False,2),
                                                       (False,True,2),(True,True,3)])
def test_inclusion_flags_are_applied(kind, completed, cancelled, count):
    query = ThreadQuery(kind, include_completed=completed, include_cancelled=cancelled)
    assert len(ThreadManager.query(threads(), query)) == count


def test_action_results_sort_before_pagination():
    query = ThreadQuery(ThreadQueryType.LIST_THREAD_ACTIONS, sort_by=ThreadSortField.TITLE,
                        sort_order=ThreadSortOrder.ASC, offset=1, limit=1)
    result = ThreadManager.query(threads(), query)
    assert result[0][0].thread_id == "done"


def test_dates_compare_instants_across_offsets():
    early = Thread("early", "Earlier", "x", created_at="2026-01-01T10:00:00+02:00")
    later = Thread("later", "Later", "x", created_at="2026-01-01T09:00:00+00:00")
    query = ThreadQuery(ThreadQueryType.LIST_THREADS, created_after="2026-01-01T08:30:00Z")
    assert ThreadManager.query([early, later], query) == [later]
    query = ThreadQuery(ThreadQueryType.LIST_THREADS, sort_by=ThreadSortField.CREATED_AT,
                        sort_order=ThreadSortOrder.ASC)
    assert ThreadManager.query([later, early], query) == [early, later]


def test_legacy_naive_dates_are_utc():
    value = Thread("t", "Title", "x", created_at="2026-01-01")
    query = ThreadQuery(ThreadQueryType.LIST_THREADS, created_after="2025-12-31T23:00:00Z")
    assert ThreadManager.query([value], query) == [value]


def test_invalid_persisted_dates_do_not_break_other_thread_queries():
    damaged = Thread("bad", "Bad", "x", created_at="not-a-date", updated_at="broken")
    valid = Thread("good", "Good", "x", created_at="2026-01-01",
                   updated_at="2026-01-02")
    query = ThreadQuery(ThreadQueryType.LIST_THREADS, created_after="2025-01-01",
                        sort_by=ThreadSortField.UPDATED_AT)
    assert ThreadManager.query([damaged, valid], query) == [valid]
    ordered = ThreadManager.query([valid, damaged], ThreadQuery(
        ThreadQueryType.LIST_THREADS, sort_by=ThreadSortField.UPDATED_AT,
        sort_order=ThreadSortOrder.ASC))
    assert ordered == [damaged, valid]


@pytest.mark.parametrize("parameters", [{"include_completed":"false"}, {"limit":True},
                                        {"created_after":"not-a-date"}])
def test_invalid_query_values_are_rejected(parameters):
    with pytest.raises(ValueError):
        ThreadManager.query([], ThreadQuery(ThreadQueryType.LIST_THREADS, **parameters))
