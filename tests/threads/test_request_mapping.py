from core.threads.models import ActionStatus, ThreadStatus
from core.threads.queries import (
    ThreadQueryType,
    ThreadSortField,
    ThreadSortOrder,
)
from core.threads.requests import ThreadRequest
from core.threads.request_mapping import build_thread_query


def test_list_open_threads_mapping():
    request = ThreadRequest.from_intent(
        ThreadQueryType.LIST_OPEN_THREADS,
    )

    query = build_thread_query(request)

    assert query.query_type == ThreadQueryType.LIST_OPEN_THREADS
    assert query.sort_by == ThreadSortField.UPDATED_AT
    assert query.sort_order == ThreadSortOrder.DESC


def test_get_thread_mapping():
    request = ThreadRequest.from_intent(
        ThreadQueryType.GET_THREAD,
        thread_id="thread-001",
    )

    query = build_thread_query(request)

    assert query.query_type == ThreadQueryType.GET_THREAD
    assert query.thread_id == "thread-001"


def test_status_mapping():
    request = ThreadRequest.from_intent(
        ThreadQueryType.LIST_THREADS_BY_STATUS,
        statuses=[ThreadStatus.IMPLEMENTATION],
    )

    query = build_thread_query(request)

    assert query.query_type == ThreadQueryType.LIST_THREADS_BY_STATUS
    assert query.statuses == [ThreadStatus.IMPLEMENTATION]

def test_list_threads_mapping():
    request = ThreadRequest.from_intent(
        ThreadQueryType.LIST_THREADS,
    )

    query = build_thread_query(request)

    assert query.query_type == ThreadQueryType.LIST_THREADS


def test_list_thread_actions_mapping():
    request = ThreadRequest.from_intent(
        ThreadQueryType.LIST_THREAD_ACTIONS,
        thread_id="thread-001",
    )

    query = build_thread_query(request)

    assert query.query_type == ThreadQueryType.LIST_THREAD_ACTIONS
    assert query.thread_id == "thread-001"


def test_list_open_actions_mapping():
    request = ThreadRequest.from_intent(
        ThreadQueryType.LIST_OPEN_ACTIONS,
        thread_id="thread-001",
    )

    query = build_thread_query(request)

    assert query.query_type == ThreadQueryType.LIST_OPEN_ACTIONS
    assert query.thread_id == "thread-001"

def test_title_filter_mapping():
    request = ThreadRequest.from_intent(
        ThreadQueryType.LIST_THREADS,
        title_contains="Eidolon",
    )

    query = build_thread_query(request)

    assert query.query_type == ThreadQueryType.LIST_THREADS
    assert query.title_contains == "Eidolon"

def test_action_status_filter_mapping():
    request = ThreadRequest.from_intent(
        ThreadQueryType.LIST_THREAD_ACTIONS,
        thread_id="thread-001",
        action_status=ActionStatus.IN_PROGRESS,
    )

    query = build_thread_query(request)

    assert query.query_type == ThreadQueryType.LIST_THREAD_ACTIONS
    assert query.thread_id == "thread-001"
    assert query.action_status == ActionStatus.IN_PROGRESS
