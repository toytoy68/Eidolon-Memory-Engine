import pytest

from core.requests import RequestEnvelope


def test_request_envelope_defaults():
    request = RequestEnvelope(
        domain="THREAD",
        intent="LIST_OPEN_THREADS",
    )

    assert request.schema_version == "0.1"
    assert request.domain == "THREAD"
    assert request.intent == "LIST_OPEN_THREADS"
    assert request.filters == {}


def test_request_envelope_with_filters():
    request = RequestEnvelope(
        domain="THREAD",
        intent="LIST_THREADS_BY_STATUS",
        filters={
            "statuses": ["IMPLEMENTATION", "TESTING"],
        },
    )

    assert request.filters["statuses"] == [
        "IMPLEMENTATION",
        "TESTING",
    ]


def test_request_envelope_rejects_unsupported_schema():
    with pytest.raises(ValueError):
        RequestEnvelope(
            domain="THREAD",
            intent="LIST_OPEN_THREADS",
            schema_version="9.9",
        )


def test_request_envelope_rejects_empty_domain():
    with pytest.raises(ValueError):
        RequestEnvelope(
            domain="",
            intent="LIST_OPEN_THREADS",
        )


def test_request_envelope_rejects_empty_intent():
    with pytest.raises(ValueError):
        RequestEnvelope(
            domain="THREAD",
            intent="",
        )


def test_request_envelope_rejects_non_object_filters():
    with pytest.raises(ValueError):
        RequestEnvelope(
            domain="THREAD",
            intent="LIST_OPEN_THREADS",
            filters=[],
        )
