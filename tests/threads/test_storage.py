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


def test_update_thread(tmp_path: Path):
    storage = ThreadStorage(tmp_path)

    thread = make_thread()
    storage.create(thread)

    thread.title = "Updated Thread"
    thread.revision = 2
    thread.updated_at = "2026-09-20T11:00:00+02:00"

    storage.update(thread)

    loaded = storage.get("thread-test-001")

    assert loaded is not None
    assert loaded.title == "Updated Thread"
    assert loaded.revision == 2
    assert loaded.updated_at == "2026-09-20T11:00:00+02:00"


def test_delete_thread(tmp_path: Path):
    storage = ThreadStorage(tmp_path)

    thread = make_thread()
    storage.create(thread)

    assert storage.exists("thread-test-001") is True

    storage.delete("thread-test-001")

    assert storage.exists("thread-test-001") is False
    assert storage.get("thread-test-001") is None


def test_list_threads(tmp_path: Path):
    storage = ThreadStorage(tmp_path)

    thread1 = make_thread()

    thread2 = Thread(
        thread_id="thread-test-002",
        title="Second Thread",
        objective="Test listing",
        status=ThreadStatus.IMPLEMENTATION,
        revision=1,
        created_at="2026-09-20T11:00:00+02:00",
        updated_at="2026-09-20T11:00:00+02:00",
    )

    storage.create(thread1)
    storage.create(thread2)

    result = storage.list()

    assert len(result) == 2
    assert {
        thread.thread_id
        for thread in result
    } == {
        "thread-test-001",
        "thread-test-002",
    }

import pytest

from core.threads.storage import (
    InvalidThreadStorageId,
    ThreadAlreadyExists,
    ThreadStorageError,
)


def test_create_duplicate_thread(tmp_path):
    storage = ThreadStorage(tmp_path)
    thread = make_thread()

    storage.create(thread)

    with pytest.raises(ThreadAlreadyExists):
        storage.create(thread)


@pytest.mark.parametrize(
    "thread_id",
    [
        "",
        "../escape",
        "thread/test",
        "thread test",
        "thread@test",
    ],
)
def test_invalid_thread_id(tmp_path, thread_id):
    storage = ThreadStorage(tmp_path)

    thread = make_thread()
    thread.thread_id = thread_id

    with pytest.raises(InvalidThreadStorageId):
        storage.create(thread)

def test_update_missing_thread(tmp_path):
    storage = ThreadStorage(tmp_path)
    thread = make_thread()

    with pytest.raises(ThreadStorageError):
        storage.update(thread)


def test_delete_missing_thread(tmp_path):
    storage = ThreadStorage(tmp_path)

    with pytest.raises(ThreadStorageError):
        storage.delete("does-not-exist")
