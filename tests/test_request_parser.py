import pytest

from core.request_parser import parse_request


def test_parse_request():
    payload = """
    {
        "request": {
            "schema_version": "0.1",
            "domain": "THREAD",
            "intent": "LIST_OPEN_THREADS",
            "filters": {}
        }
    }
    """

    request = parse_request(payload)

    assert request.schema_version == "0.1"
    assert request.domain == "THREAD"
    assert request.intent == "LIST_OPEN_THREADS"
    assert request.filters == {}


def test_parse_request_with_filters():
    payload = """
    {
        "request": {
            "schema_version": "0.1",
            "domain": "THREAD",
            "intent": "GET_THREAD",
            "filters": {
                "thread_id": "thread-001"
            }
        }
    }
    """

    request = parse_request(payload)

    assert request.filters["thread_id"] == "thread-001"


def test_parse_request_rejects_invalid_json():
    with pytest.raises(ValueError):
        parse_request("{invalid")


def test_parse_request_requires_object():
    with pytest.raises(ValueError):
        parse_request("[]")


def test_parse_request_requires_request():
    with pytest.raises(ValueError):
        parse_request("{}")


def test_parse_request_requires_request_object():
    with pytest.raises(ValueError):
        parse_request('{"request": []}')


def test_parse_request_requires_required_fields():
    with pytest.raises(ValueError):
        parse_request(
            '{"request": {"domain": "THREAD", "intent": "LIST_OPEN_THREADS"}}'
        )


def test_parse_request_rejects_non_object_filters():
    with pytest.raises(ValueError):
        parse_request(
            """
            {
                "request": {
                    "schema_version": "0.1",
                    "domain": "THREAD",
                    "intent": "LIST_OPEN_THREADS",
                    "filters": []
                }
            }
            """
        )


def test_parse_request_defaults_filters():
    request = parse_request(
        """
        {
            "request": {
                "schema_version": "0.1",
                "domain": "THREAD",
                "intent": "LIST_OPEN_THREADS"
            }
        }
        """
    )

    assert request.filters == {}
