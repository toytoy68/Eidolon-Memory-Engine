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

    assert len(result) == 1
    assert result[0].thread_id == "thread-dispatch-001"


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
