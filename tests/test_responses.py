import pytest

from core.responses import ResponseEnvelope


def test_response_envelope_defaults():
    response = ResponseEnvelope(
        domain="THREAD",
        intent="LIST_OPEN_THREADS",
        status="OK",
    )

    assert response.schema_version == "0.1"
    assert response.domain == "THREAD"
    assert response.intent == "LIST_OPEN_THREADS"
    assert response.status == "OK"
    assert response.data == {}


def test_response_envelope_with_data():
    response = ResponseEnvelope(
        domain="THREAD",
        intent="LIST_OPEN_THREADS",
        status="OK",
        data=[
            {"thread_id": "thread-001"},
        ],
    )

    assert response.data == [
        {"thread_id": "thread-001"},
    ]


def test_response_envelope_error():
    response = ResponseEnvelope(
        domain="THREAD",
        intent="GET_THREAD",
        status="ERROR",
        data={"error": "Thread not found"},
    )

    assert response.status == "ERROR"
    assert response.data["error"] == "Thread not found"


def test_response_envelope_rejects_unsupported_schema():
    with pytest.raises(ValueError):
        ResponseEnvelope(
            domain="THREAD",
            intent="LIST_OPEN_THREADS",
            status="OK",
            schema_version="9.9",
        )


def test_response_envelope_rejects_empty_domain():
    with pytest.raises(ValueError):
        ResponseEnvelope(
            domain="",
            intent="LIST_OPEN_THREADS",
            status="OK",
        )


def test_response_envelope_rejects_empty_intent():
    with pytest.raises(ValueError):
        ResponseEnvelope(
            domain="THREAD",
            intent="",
            status="OK",
        )


def test_response_envelope_rejects_unknown_status():
    with pytest.raises(ValueError):
        ResponseEnvelope(
            domain="THREAD",
            intent="LIST_OPEN_THREADS",
            status="UNKNOWN",
        )


def test_response_envelope_to_dict():
    response = ResponseEnvelope(
        domain="THREAD",
        intent="LIST_OPEN_THREADS",
        status="OK",
        data=[
            {"thread_id": "thread-001"},
        ],
    )

    payload = response.to_dict()

    assert payload["response"]["schema_version"] == "0.1"
    assert payload["response"]["domain"] == "THREAD"
    assert payload["response"]["intent"] == "LIST_OPEN_THREADS"
    assert payload["response"]["status"] == "OK"
    assert payload["response"]["data"][0]["thread_id"] == "thread-001"


def test_response_envelope_to_json():
    response = ResponseEnvelope(
        domain="THREAD",
        intent="GET_THREAD",
        status="OK",
        data={"thread_id": "thread-001"},
    )

    payload = response.to_json()

    assert '"schema_version": "0.1"' in payload
    assert '"domain": "THREAD"' in payload
    assert '"intent": "GET_THREAD"' in payload
    assert '"status": "OK"' in payload
    assert '"thread_id": "thread-001"' in payload
