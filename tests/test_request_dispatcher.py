import pytest

from core.request_dispatcher import RequestDispatcher
from core.requests import RequestEnvelope
from core.threads.models import Thread, ThreadStatus
from core.threads.service import ThreadService
from core.threads.storage import ThreadStorage


def make_thread() -> Thread:
    return Thread(
        thread_id="thread-dispatch-001",
        title="Dispatcher Thread",
        objective="Test request dispatcher",
        status=ThreadStatus.IMPLEMENTATION,
        revision=1,
        created_at="2026-09-20T10:00:00+02:00",
        updated_at="2026-09-20T11:00:00+02:00",
    )


def test_dispatch_thread_request(tmp_path):
    storage = ThreadStorage(tmp_path)
    storage.create(make_thread())

    service = ThreadService(storage)
    dispatcher = RequestDispatcher(service)

    envelope = RequestEnvelope(
        domain="THREAD",
        intent="LIST_OPEN_THREADS",
    )

    result = dispatcher.execute(envelope)

    assert result.schema_version == "0.1"
    assert result.domain == "THREAD"
    assert result.intent == "LIST_OPEN_THREADS"
    assert result.status == "OK"
    assert len(result.data) == 1
    assert result.data[0]["thread_id"] == "thread-dispatch-001"


def test_dispatch_rejects_unknown_domain(tmp_path):
    storage = ThreadStorage(tmp_path)
    service = ThreadService(storage)
    dispatcher = RequestDispatcher(service)

    envelope = RequestEnvelope(
        domain="UNKNOWN",
        intent="LIST_OPEN_THREADS",
    )

    with pytest.raises(ValueError):
        dispatcher.execute(envelope)


def test_json_request_to_json_response(tmp_path):
    from core.request_parser import parse_request

    storage = ThreadStorage(tmp_path)
    storage.create(make_thread())

    service = ThreadService(storage)
    dispatcher = RequestDispatcher(service)

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

    envelope = parse_request(payload)
    response = dispatcher.execute(envelope)
    output = response.to_json()

    assert '"schema_version": "0.1"' in output
    assert '"domain": "THREAD"' in output
    assert '"intent": "LIST_OPEN_THREADS"' in output
    assert '"status": "OK"' in output
    assert '"thread_id": "thread-dispatch-001"' in output


def test_json_status_filter_maps_wire_value_before_query(tmp_path):
    from core.request_parser import parse_request
    storage = ThreadStorage(tmp_path)
    storage.create(make_thread())
    dispatcher = RequestDispatcher(ThreadService(storage))
    payload = ('{"request":{"schema_version":"0.1","domain":"THREAD",'
               '"intent":"LIST_THREADS_BY_STATUS","filters":{'
               '"statuses":["IMPLEMENTATION"],"sort_by":"title",'
               '"sort_order":"ASC"}}}')

    response = dispatcher.execute(parse_request(payload))
    assert [item["thread_id"] for item in response.data] == ["thread-dispatch-001"]


def test_invalid_json_thread_filter_fails_before_storage_read(tmp_path, monkeypatch):
    from core.request_parser import parse_request
    storage = ThreadStorage(tmp_path)
    monkeypatch.setattr(storage, "list", lambda: pytest.fail("storage read before validation"))
    dispatcher = RequestDispatcher(ThreadService(storage))
    payload = ('{"request":{"schema_version":"0.1","domain":"THREAD",'
               '"intent":"LIST_THREADS_BY_STATUS","filters":{'
               '"statuses":["INVALID_PRIVATE_VALUE"]}}}')

    with pytest.raises(ValueError, match="Invalid Thread request filters"):
        dispatcher.execute(parse_request(payload))
