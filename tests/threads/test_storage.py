from pathlib import Path

from core.threads.models import Thread, ThreadAction, ThreadStatus
from core.threads.storage import ThreadStorage
from core.threads.storage import ThreadStorageError
from core.threads.manager import InvalidThread, ThreadManager
from core.backend.filesystem import FilesystemBackend
from core.backend.models import Memory
import pytest
from dataclasses import replace


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


def test_direct_thread_create_requires_existing_linked_information(tmp_path):
    storage = ThreadStorage(tmp_path / "persistent")
    linked = replace(make_thread(), relations=[{"type": "CONCERNS", "target_id": "info-1"}])
    with pytest.raises(ThreadStorageError, match="missing linked Information"):
        storage.create(linked)
    assert not storage.exists(linked.thread_id)
    backend = FilesystemBackend(tmp_path / "persistent", tmp_path / "history")
    backend.store(Memory("info-1"))
    storage.create(linked)
    assert storage.get(linked.thread_id) == linked


def test_direct_thread_update_cannot_change_concerns(tmp_path):
    storage = ThreadStorage(tmp_path / "persistent")
    original = make_thread()
    storage.create(original)
    changed = replace(original, revision=2, relations=[{"type": "CONCERNS", "target_id": "info-1"}])
    with pytest.raises(ThreadStorageError, match="coordinated writer"):
        storage.update(changed, 1)
    assert storage.get(original.thread_id) == original


def test_create_rejects_lossy_nested_thread_context(tmp_path):
    storage = ThreadStorage(tmp_path / "persistent")
    thread = replace(make_thread(), context={"sequence": ("first", "second")})
    with pytest.raises(ThreadStorageError, match="changes during serialization"):
        storage.create(thread)
    assert not storage.exists(thread.thread_id)


def test_update_rejects_unreadable_thread_without_changing_disk(tmp_path):
    storage = ThreadStorage(tmp_path / "persistent")
    original = make_thread()
    storage.create(original)
    path = storage._path(original.thread_id)
    before = path.read_bytes()
    changed = replace(original, revision=2, actions=["not an action"])
    with pytest.raises(ThreadStorageError, match="invalid Thread document"):
        storage.update(changed, 1)
    assert path.read_bytes() == before


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


def test_thread_storage_rejects_symlink_without_reading_or_deleting_target(tmp_path):
    storage = ThreadStorage(tmp_path / "persistent")
    outside = tmp_path / "outside.md"
    outside.write_text(storage._serialize(make_thread()))
    path = storage.threads_root / "thread-test-001.md"
    path.symlink_to(outside)
    original = outside.read_bytes()
    with pytest.raises(ThreadStorageError, match="symlink"):
        storage.get("thread-test-001")
    with pytest.raises(ThreadStorageError, match="symlink"):
        storage.exists("thread-test-001")
    with pytest.raises(ThreadStorageError, match="symlink"):
        storage.list()
    with pytest.raises(ThreadStorageError, match="symlink"):
        storage.delete("thread-test-001")
    assert outside.read_bytes() == original
    assert path.is_symlink()


def test_thread_storage_rejects_symlink_directory(tmp_path):
    persistent = tmp_path / "persistent"
    persistent.mkdir()
    external = tmp_path / "external"
    external.mkdir()
    (persistent / "threads").symlink_to(external, target_is_directory=True)
    with pytest.raises(ThreadStorageError, match="directory is a symlink"):
        ThreadStorage(persistent)


def test_thread_storage_rejects_linked_persistent_root_before_creating_threads(tmp_path):
    external = tmp_path / "external"
    external.mkdir()
    persistent = tmp_path / "persistent"
    persistent.symlink_to(external, target_is_directory=True)
    with pytest.raises(ThreadStorageError, match="directory is a symlink"):
        ThreadStorage(persistent)
    assert not (external / "threads").exists()


def test_thread_revisions_reject_booleans_before_writing(tmp_path):
    storage = ThreadStorage(tmp_path / "persistent")
    wrong = replace(make_thread(), revision=True)
    with pytest.raises(InvalidThread, match="revision must be an integer"):
        ThreadManager.validate(wrong)
    with pytest.raises(ThreadStorageError, match="revision must be an integer"):
        storage.create(wrong)
    assert not storage.exists(wrong.thread_id)
    storage.create(make_thread())
    with pytest.raises(ThreadStorageError, match="previous_revision"):
        storage.update(replace(make_thread(), revision=2), previous_revision=True)
    with pytest.raises(ThreadStorageError, match="revision must be an integer"):
        storage.update(replace(make_thread(), revision=True), previous_revision=1)
    assert storage.get(wrong.thread_id).revision == 1


@pytest.mark.parametrize("field,value,message", [
    ("thread_id", 1, "thread_id is required"),
    ("title", 1, "title is required"),
    ("objective", None, "objective is required"),
    ("created_at", 1, "created_at is required"),
    ("updated_at", None, "updated_at is required"),
    ("started_at", 1, "started_at must be text"),
    ("completed_at", 1, "completed_at must be text"),
    ("context", [], "context must be an object"),
    ("provenance", [], "provenance must be an object"),
    ("actions", "invalid", "actions must be a list"),
    ("actions", ["invalid"], "actions must contain ThreadAction"),
    ("actions", [ThreadAction("a", "task", status="PLANNED")], "invalid action status"),
    ("actions", [ThreadAction("a", "task", metadata=[])], "invalid action metadata"),
    ("relations", "invalid", "relations must be a list"),
])
def test_thread_domain_validation_rejects_malformed_fields(field, value, message):
    with pytest.raises(InvalidThread, match=message):
        ThreadManager.validate(replace(make_thread(), **{field: value}))


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

    storage.update(
        thread,
        previous_revision=1,
    )

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
    ThreadRevisionConflict,
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


@pytest.mark.parametrize("thread_id", [1, True, None, []])
def test_nontext_thread_id_uses_storage_error_without_writing(tmp_path, thread_id):
    storage = ThreadStorage(tmp_path)
    thread = make_thread()
    thread.thread_id = thread_id
    with pytest.raises(InvalidThreadStorageId):
        storage.create(thread)
    with pytest.raises(InvalidThreadStorageId):
        storage.get(thread_id)
    assert not list(storage.threads_root.glob("*.md"))

def test_update_missing_thread(tmp_path):
    storage = ThreadStorage(tmp_path)
    thread = make_thread()

    with pytest.raises(ThreadStorageError):
        storage.update(
            thread,
            previous_revision=1,
        )


def test_delete_missing_thread(tmp_path):
    storage = ThreadStorage(tmp_path)

    with pytest.raises(ThreadStorageError):
        storage.delete("does-not-exist")


def test_update_rejects_stale_previous_revision(tmp_path):
    storage = ThreadStorage(tmp_path)

    thread = make_thread()
    storage.create(thread)

    updated = make_thread()
    updated.title = "Updated Thread"
    updated.revision = 2

    with pytest.raises(ThreadRevisionConflict):
        storage.update(
            updated,
            previous_revision=0,
        )


def test_update_rejects_invalid_next_revision(tmp_path):
    storage = ThreadStorage(tmp_path)

    thread = make_thread()
    storage.create(thread)

    updated = make_thread()
    updated.title = "Updated Thread"
    updated.revision = 3

    with pytest.raises(ThreadRevisionConflict):
        storage.update(
            updated,
            previous_revision=1,
        )
