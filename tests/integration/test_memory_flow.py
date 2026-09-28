"""Exercise real repositories together on an isolated memory tree."""

import pytest

from core.backend.filesystem import FilesystemBackend
from core.backend.models import Memory
from core.events.filesystem import FilesystemEventRepository
from core.operations.filesystem import FilesystemOperationRepository
from core.operations.models import OperationStatus
from core.operations.thread_status import FilesystemThreadOperations
from core.threads.models import Thread, ThreadStatus
from core.threads.storage import ThreadStorage


def open_engine(root):
    persistent = root / "memory" / "persistent"
    history = root / "memory" / "history"
    backend = FilesystemBackend(persistent, history)
    threads = ThreadStorage(persistent)
    operations = FilesystemOperationRepository(history / "operations" / "thread-status-v1")
    events = FilesystemEventRepository(history / "events" / "thread-status-v1")
    return backend, FilesystemThreadOperations(threads, events, operations)


def test_information_and_thread_survive_interrupted_status_commit(tmp_path, monkeypatch):
    backend, engine = open_engine(tmp_path)
    original = Memory("info-1", content="A paragraph with **Markdown**.",
                      metadata={"type": "FACT"})
    backend.store(original)
    thread = Thread(
        "thread-1", "Review information", "Validate info-1",
        relations=[{"type": "CONCERNS", "target_id": "info-1"}],
        created_at="2026-09-28T00:00:00+00:00",
        updated_at="2026-09-28T00:00:00+00:00",
    )
    engine.storage.create(thread)

    save = engine.events.save

    def interrupt_after_event(event):
        save(event)
        raise InterruptedError("simulated interruption after durable Event write")

    monkeypatch.setattr(engine.events, "save", interrupt_after_event)
    with pytest.raises(InterruptedError):
        engine.change_status("thread-1", ThreadStatus.VALIDATED,
                             previous_revision=1, operation_id="op-1", event_id="event-1")

    backend, restarted = open_engine(tmp_path)
    assert restarted.operations.get("op-1").status is OperationStatus.APPLYING
    assert restarted.recover() == {"op-1": {"status": "COMMITTED"}}
    result = restarted.storage.get("thread-1")
    assert result.status is ThreadStatus.VALIDATED
    assert result.revision == 2
    assert result.relations == thread.relations
    assert backend.get("info-1") == original

    event, = restarted.events.list_for_target("thread-1")
    assert event.event_id == "event-1"
    assert event.revision == result.revision
    assert restarted.operations.get("op-1").status is OperationStatus.COMMITTED
    assert restarted.change_status("thread-1", ThreadStatus.VALIDATED,
                                    previous_revision=1, operation_id="op-1",
                                    event_id="event-1") == result
    assert restarted.recover() == {}
    assert len(restarted.events.list_for_target("thread-1")) == 1
