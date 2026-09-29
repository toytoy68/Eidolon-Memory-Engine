import pytest

from core.backend.errors import InvalidMemory
from core.backend.filesystem import FilesystemBackend
from core.events.errors import InvalidEvent
from core.events.filesystem import FilesystemEventRepository
from core.operations.errors import InvalidOperationRecord
from core.operations.filesystem import FilesystemOperationRepository
from core.threads.storage import ThreadStorage, ThreadStorageError


def test_repositories_report_corrupt_utf8_without_following_other_data(tmp_path):
    backend = FilesystemBackend(tmp_path / "persistent", tmp_path / "history")
    threads = ThreadStorage(backend.persistent_root)
    events = FilesystemEventRepository(tmp_path / "events")
    operations = FilesystemOperationRepository(tmp_path / "operations")
    (backend.persistent_root / "info.md").write_bytes(b"\xff")
    (threads.threads_root / "thread.md").write_bytes(b"\xff")
    (events.events_root / "event.md").write_bytes(b"\xff")
    (operations.root / "op.json").write_bytes(b"\xff")

    with pytest.raises(InvalidMemory, match="unable to read memory"):
        backend.get("info")
    assert backend.list() == []
    with pytest.raises(ThreadStorageError, match="unable to read Thread"):
        threads.get("thread")
    with pytest.raises(ThreadStorageError, match="unable to read Thread"):
        threads.list()
    with pytest.raises(InvalidEvent, match="unable to read Event"):
        events.get("event")
    with pytest.raises(InvalidEvent, match="unable to read Event"):
        events.list_for_target("info")
    with pytest.raises(InvalidOperationRecord):
        operations.get("op")
