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

def test_action_statuses_filter_mapping():
    request = ThreadRequest.from_intent(
        ThreadQueryType.LIST_THREAD_ACTIONS,
        thread_id="thread-001",
        action_statuses=[
            ActionStatus.PLANNED,
            ActionStatus.IN_PROGRESS,
        ],
    )

    query = build_thread_query(request)

    assert query.query_type == ThreadQueryType.LIST_THREAD_ACTIONS
    assert query.thread_id == "thread-001"
    assert query.action_statuses == [
        ActionStatus.PLANNED,
        ActionStatus.IN_PROGRESS,
    ]

def test_relation_filter_mapping():
    request = ThreadRequest.from_intent(
        ThreadQueryType.LIST_THREADS,
        relation_type="DEPENDS_ON",
        related_to="thread-002",
    )

    query = build_thread_query(request)

    assert query.query_type == ThreadQueryType.LIST_THREADS
    assert query.relation_type == "DEPENDS_ON"
    assert query.related_to == "thread-002"

def test_provenance_filter_mapping():
    request = ThreadRequest.from_intent(
        ThreadQueryType.LIST_THREADS,
        provenance={
            "source": "conversation",
            "origin": "eidolon",
        },
    )

    query = build_thread_query(request)

    assert query.query_type == ThreadQueryType.LIST_THREADS
    assert query.provenance == {
        "source": "conversation",
        "origin": "eidolon",
    }

def test_created_date_filters_mapping():
    request = ThreadRequest.from_intent(
        ThreadQueryType.LIST_THREADS,
        created_after="2026-09-01T00:00:00+02:00",
        created_before="2026-09-20T23:59:59+02:00",
    )

    query = build_thread_query(request)

    assert query.query_type == ThreadQueryType.LIST_THREADS
    assert query.created_after == "2026-09-01T00:00:00+02:00"
    assert query.created_before == "2026-09-20T23:59:59+02:00"

def test_updated_date_filters_mapping():
    request = ThreadRequest.from_intent(
        ThreadQueryType.LIST_THREADS,
        updated_after="2026-09-10T00:00:00+02:00",
        updated_before="2026-09-20T23:59:59+02:00",
    )

    query = build_thread_query(request)

    assert query.query_type == ThreadQueryType.LIST_THREADS
    assert query.updated_after == "2026-09-10T00:00:00+02:00"
    assert query.updated_before == "2026-09-20T23:59:59+02:00"

def test_started_date_filters_mapping():
    request = ThreadRequest.from_intent(
        ThreadQueryType.LIST_THREADS,
        started_after="2026-09-15T00:00:00+02:00",
        started_before="2026-09-20T23:59:59+02:00",
    )

    query = build_thread_query(request)

    assert query.query_type == ThreadQueryType.LIST_THREADS
    assert query.started_after == "2026-09-15T00:00:00+02:00"
    assert query.started_before == "2026-09-20T23:59:59+02:00"

def test_include_status_filters_mapping():
    request = ThreadRequest.from_intent(
        ThreadQueryType.LIST_THREADS,
        include_completed=True,
        include_cancelled=True,
    )

    query = build_thread_query(request)

    assert query.query_type == ThreadQueryType.LIST_THREADS
    assert query.include_completed is True
    assert query.include_cancelled is True

def test_sort_mapping():
    request = ThreadRequest.from_intent(
        ThreadQueryType.LIST_THREADS,
        sort_by=ThreadSortField.TITLE,
        sort_order=ThreadSortOrder.ASC,
    )

    query = build_thread_query(request)

    assert query.query_type == ThreadQueryType.LIST_THREADS
    assert query.sort_by == ThreadSortField.TITLE
    assert query.sort_order == ThreadSortOrder.ASC

def test_pagination_mapping():
    request = ThreadRequest.from_intent(
        ThreadQueryType.LIST_THREADS,
        limit=50,
        offset=100,
    )

    query = build_thread_query(request)

    assert query.query_type == ThreadQueryType.LIST_THREADS
    assert query.limit == 50
    assert query.offset == 100
