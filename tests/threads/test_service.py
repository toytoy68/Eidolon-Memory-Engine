import pytest

from core.backend.filesystem import FilesystemBackend
from core.backend.models import Memory
from core.events.filesystem import FilesystemEventRepository
from core.operations.filesystem import FilesystemOperationRepository
from core.operations.thread_create import FilesystemLinkedThreadCreation
from core.threads.models import Thread, ThreadStatus
from core.threads.queries import (
    ThreadQuery,
    ThreadQueryType,
)
from core.threads.service import ThreadService
from core.threads.storage import ThreadStorage
from core.threads.requests import ThreadRequest


def make_thread() -> Thread:
    return Thread(
        thread_id="thread-service-001",
        title="Service Thread",
        objective="Test ThreadService",
        status=ThreadStatus.IMPLEMENTATION,
        revision=1,
        created_at="2026-09-20T10:00:00+02:00",
        updated_at="2026-09-20T11:00:00+02:00",
    )


def test_get_thread(tmp_path):
    storage = ThreadStorage(tmp_path)
    thread = make_thread()
    storage.create(thread)

    service = ThreadService(storage)

    result = service.get("thread-service-001")

    assert result is not None
    assert result.thread_id == "thread-service-001"
    assert result.title == "Service Thread"


def test_query_threads(tmp_path):
    storage = ThreadStorage(tmp_path)
    thread = make_thread()
    storage.create(thread)

    service = ThreadService(storage)

    query = ThreadQuery(
        query_type=ThreadQueryType.LIST_OPEN_THREADS,
    )

    result = service.query(query)

    assert len(result) == 1
    assert result[0].thread_id == "thread-service-001"



def test_execute_thread_request(tmp_path):
    storage = ThreadStorage(tmp_path)
    thread = make_thread()
    storage.create(thread)

    service = ThreadService(storage)

    request = ThreadRequest.from_intent(
        ThreadQueryType.LIST_OPEN_THREADS,
    )

    result = service.execute(request)

    assert len(result) == 1
    assert result[0].thread_id == "thread-service-001"




def test_execute_envelope(tmp_path):
    from core.requests import RequestEnvelope

    storage = ThreadStorage(tmp_path)
    thread = make_thread()
    storage.create(thread)

    service = ThreadService(storage)

    envelope = RequestEnvelope(
        domain="THREAD",
        intent="LIST_OPEN_THREADS",
    )

    result = service.execute_envelope(envelope)

    assert len(result) == 1
    assert result[0].thread_id == "thread-service-001"


def test_execute_parsed_json_request(tmp_path):
    from core.request_parser import parse_request

    storage = ThreadStorage(tmp_path)
    thread = make_thread()
    storage.create(thread)

    service = ThreadService(storage)

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
    result = service.execute_envelope(envelope)

    assert len(result) == 1
    assert result[0].thread_id == "thread-service-001"


def test_create_linked_requires_coordinator(tmp_path):
    service = ThreadService(ThreadStorage(tmp_path))
    with pytest.raises(RuntimeError, match="operation coordinator"):
        service.create_linked(make_thread(), "info-1", operation_id="op-1", event_id="event-1")


def test_create_linked_through_service_records_event(tmp_path):
    persistent = tmp_path / "persistent"
    history = tmp_path / "history"
    backend = FilesystemBackend(persistent, history)
    backend.store(Memory("info-1"))
    storage = ThreadStorage(persistent)
    events = FilesystemEventRepository(history / "events/thread-create-v1")
    operations = FilesystemOperationRepository(history / "operations/thread-create-v1")
    creation = FilesystemLinkedThreadCreation(backend, storage, events, operations)
    service = ThreadService(storage, creation=creation)

    linked = service.create_linked(make_thread(), "info-1",
                                   operation_id="op-1", event_id="event-1")
    assert storage.get(linked.thread_id) == linked
    assert linked.relations == [{"type": "CONCERNS", "target_id": "info-1"}]
    assert events.get("event-1").thread_id == linked.thread_id
    assert service.create_linked(make_thread(), "info-1",
                                 operation_id="op-1", event_id="event-1") == linked
