from core.threads.models import ActionStatus, ThreadStatus
from core.threads.queries import (
    ThreadQuery,
    ThreadQueryType,
    ThreadSortField,
    ThreadSortOrder,
)


def test_list_open_threads():
    query = ThreadQuery(
        query_type=ThreadQueryType.LIST_OPEN_THREADS,
        statuses=[
            ThreadStatus.IMPLEMENTATION,
            ThreadStatus.TESTING,
        ],
        sort_by=ThreadSortField.UPDATED_AT,
        sort_order=ThreadSortOrder.DESC,
        limit=10,
    )

    query.validate()

    assert query.normalized_statuses() == [
        ThreadStatus.IMPLEMENTATION,
        ThreadStatus.TESTING,
    ]


def test_action_status_normalization():
    query = ThreadQuery(
        query_type=ThreadQueryType.LIST_OPEN_ACTIONS,
        action_status=ActionStatus.IN_PROGRESS,
        action_statuses=[
            ActionStatus.IN_PROGRESS,
            ActionStatus.PLANNED,
        ],
    )

    query.validate()

    assert query.normalized_action_statuses() == [
        ActionStatus.IN_PROGRESS,
        ActionStatus.PLANNED,
    ]


def test_get_thread_requires_id():
    query = ThreadQuery(
        query_type=ThreadQueryType.GET_THREAD,
    )

    try:
        query.validate()
    except ValueError as exc:
        assert "thread_id is required" in str(exc)
    else:
        raise AssertionError("Expected ValueError")


def test_status_query_requires_status():
    query = ThreadQuery(
        query_type=ThreadQueryType.LIST_THREADS_BY_STATUS,
    )

    try:
        query.validate()
    except ValueError as exc:
        assert "status or statuses is required" in str(exc)
    else:
        raise AssertionError("Expected ValueError")


def test_query_limits():
    query = ThreadQuery(
        query_type=ThreadQueryType.LIST_THREADS,
        limit=1001,
    )

    try:
        query.validate()
    except ValueError as exc:
        assert "limit must be <= 1000" in str(exc)
    else:
        raise AssertionError("Expected ValueError")
