from pathlib import Path

from core.threads.models import Thread, ThreadStatus
from core.threads.storage import ThreadStorage


def make_thread() -> Thread:
    return Thread(
        thread_id="thread-test-001",
        title="Test Thread",
        objective="Validate Thread persistence",
        status=ThreadStatus.PROPOSED,
        revision=1,
        context={
            "source": "unit-test",
        },
        created_at="2026-09-20T10:00:00+02:00",
        updated_at="2026-09-20T10:00:00+02:00",
        provenance={
            "created_by": "test",
        },
    )


def test_create_thread(tmp_path: Path):
    storage = ThreadStorage(tmp_path)

    thread = make_thread()

    storage.create(thread)

    path = tmp_path / "threads" / "thread-test-001.md"

    assert path.exists()


def test_get_thread(tmp_path: Path):
    storage = ThreadStorage(tmp_path)

    thread = make_thread()

    storage.create(thread)

    loaded = storage.get("thread-test-001")

    assert loaded is not None
    assert loaded.thread_id == thread.thread_id
    assert loaded.title == thread.title
    assert loaded.objective == thread.objective
    assert loaded.status == thread.status
    assert loaded.revision == thread.revision
    assert loaded.context == thread.context
    assert loaded.provenance == thread.provenance


def test_exists(tmp_path: Path):
    storage = ThreadStorage(tmp_path)

    thread = make_thread()

    assert storage.exists("thread-test-001") is False

    storage.create(thread)

    assert storage.exists("thread-test-001") is True


def test_get_missing_thread(tmp_path: Path):
    storage = ThreadStorage(tmp_path)

    assert storage.get("does-not-exist") is None
