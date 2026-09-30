from dataclasses import replace

import pytest

from core.backend.filesystem import FilesystemBackend
from core.backend.models import Memory
from core.threads.link_service import MissingLinkedInformation, ThreadInformationLinkService
from core.threads.models import Thread
from core.threads.storage import ThreadStorage


def service(root):
    persistent = root / "persistent"
    backend = FilesystemBackend(persistent, root / "history")
    storage = ThreadStorage(persistent)
    return backend, storage, ThreadInformationLinkService(backend, storage)


def thread():
    return Thread("thread-1", "Title", "Objective", created_at="2026-09-28",
                  updated_at="2026-09-28")


def test_create_validates_target_and_persists_link(tmp_path):
    backend, storage, links = service(tmp_path)
    backend.store(Memory("info-1", content="source"))
    original = thread()

    linked = links.create(original, "info-1")

    assert original.relations == []
    assert linked.relations == [{"type": "CONCERNS", "target_id": "info-1"}]
    assert storage.get("thread-1") == linked
    assert backend.get("info-1").content == "source"


def test_missing_information_does_not_create_thread(tmp_path):
    _, storage, links = service(tmp_path)
    with pytest.raises(MissingLinkedInformation):
        links.create(thread(), "missing")
    assert storage.get("thread-1") is None


def test_duplicate_link_is_not_added_twice(tmp_path):
    backend, storage, links = service(tmp_path)
    backend.store(Memory("info-1"))
    existing = replace(thread(), relations=[{"type": "CONCERNS", "target_id": "info-1"}])
    links.create(existing, "info-1")
    assert storage.get("thread-1").relations == existing.relations


def test_legacy_target_link_is_not_added_twice(tmp_path):
    backend, storage, links = service(tmp_path)
    backend.store(Memory("info-1"))
    existing = replace(thread(), relations=[{"type": "CONCERNS", "target": "info-1"}])

    linked = links.create(existing, "info-1")

    assert linked.relations == existing.relations
    assert storage.get("thread-1").relations == existing.relations


def test_link_service_rejects_different_persistent_roots(tmp_path):
    backend = FilesystemBackend(tmp_path / "one", tmp_path / "history")
    storage = ThreadStorage(tmp_path / "two")
    with pytest.raises(ValueError, match="share"):
        ThreadInformationLinkService(backend, storage)
