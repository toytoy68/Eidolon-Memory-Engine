from core.threads.models import Thread, ThreadStatus
from core.threads.queries import (
    ThreadQuery,
    ThreadQueryType,
)
from core.threads.service import ThreadService
from core.threads.storage import ThreadStorage


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
