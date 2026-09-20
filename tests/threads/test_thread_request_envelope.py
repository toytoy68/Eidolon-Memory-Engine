import pytest

from core.requests import RequestEnvelope
from core.threads.queries import ThreadQueryType
from core.threads.request_envelope import build_thread_request


def test_build_thread_request():
    envelope = RequestEnvelope(
        domain="THREAD",
        intent="LIST_OPEN_THREADS",
    )

    request = build_thread_request(envelope)

    assert request.domain == "THREAD"
    assert request.intent == ThreadQueryType.LIST_OPEN_THREADS
    assert request.query.query_type == ThreadQueryType.LIST_OPEN_THREADS


def test_build_thread_request_passes_filters():
    envelope = RequestEnvelope(
        domain="THREAD",
        intent="GET_THREAD",
        filters={"thread_id": "thread-001"},
    )

    request = build_thread_request(envelope)

    assert request.query.thread_id == "thread-001"


def test_build_thread_request_rejects_other_domain():
    envelope = RequestEnvelope(
        domain="INFORMATION",
        intent="LIST_OPEN_THREADS",
    )

    with pytest.raises(ValueError):
        build_thread_request(envelope)


def test_build_thread_request_rejects_unknown_intent():
    envelope = RequestEnvelope(
        domain="THREAD",
        intent="UNKNOWN_INTENT",
    )

    with pytest.raises(ValueError):
        build_thread_request(envelope)


def test_build_thread_request_preserves_query_filters():
    envelope = RequestEnvelope(
        domain="THREAD",
        intent="LIST_THREADS_BY_STATUS",
        filters={
            "statuses": ["IMPLEMENTATION", "TESTING"],
            "limit": 10,
            "offset": 5,
        },
    )

    request = build_thread_request(envelope)

    assert request.query.statuses == ["IMPLEMENTATION", "TESTING"]
    assert request.query.limit == 10
    assert request.query.offset == 5
