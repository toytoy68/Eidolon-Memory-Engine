import pytest

from core.threads.queries import ThreadQuery, ThreadQueryType
from core.threads.requests import ThreadRequest


def test_thread_request_creation():
    query = ThreadQuery(
        query_type=ThreadQueryType.LIST_OPEN_THREADS,
    )

    request = ThreadRequest(
        intent=ThreadQueryType.LIST_OPEN_THREADS,
        query=query,
    )

    assert request.domain == "THREAD"
    assert request.intent == ThreadQueryType.LIST_OPEN_THREADS
    assert request.query is query


def test_thread_request_requires_matching_intent():
    query = ThreadQuery(
        query_type=ThreadQueryType.LIST_OPEN_THREADS,
    )

    with pytest.raises(ValueError):
        ThreadRequest(
            intent=ThreadQueryType.LIST_THREADS,
            query=query,
        )

def test_thread_request_from_intent():
    request = ThreadRequest.from_intent(
        ThreadQueryType.GET_THREAD,
        thread_id="thread-001",
    )

    assert request.domain == "THREAD"
    assert request.intent == ThreadQueryType.GET_THREAD
    assert request.query.query_type == ThreadQueryType.GET_THREAD
    assert request.query.thread_id == "thread-001"
