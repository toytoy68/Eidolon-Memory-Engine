import json

import pytest

from core.backend.filesystem import FilesystemBackend
from core.backend.models import Memory
from core.information.deletion_service import (
    InformationDeletionBlocked, LinkedInformationDeletionService,
)
from core.threads.link_service import ThreadInformationLinkService
from core.threads.models import Thread
from core.threads.storage import ThreadStorage


def stores(tmp_path):
    persistent = tmp_path / "persistent"
    backend = FilesystemBackend(persistent, tmp_path / "history")
    threads = ThreadStorage(persistent)
    return backend, threads, LinkedInformationDeletionService(backend, threads)


def test_guarded_approval_preserves_linked_information_and_pending_request(tmp_path):
    backend, threads, deletion = stores(tmp_path)
    backend.store(Memory("info-1", content="important"))
    ThreadInformationLinkService(backend, threads).create(
        Thread("thread-1", "Title", "Objective", created_at="2026-09-28",
               updated_at="2026-09-28"), "info-1")
    backend.delete_request("info-1", "human", "reason", 1, "delete-1")

    with pytest.raises(InformationDeletionBlocked, match="linked"):
        deletion.approve_delete("info-1", "delete-1")

    assert backend.get("info-1").content == "important"
    request = json.loads((tmp_path / "history/pending-delete/info-1.json").read_text())
    assert request["status"] == "PENDING_DELETE"


def test_guarded_approval_allows_unlinked_information(tmp_path):
    backend, threads, deletion = stores(tmp_path)
    backend.store(Memory("info-1"))
    backend.store(Memory("info-2"))
    ThreadInformationLinkService(backend, threads).create(
        Thread("thread-1", "Title", "Objective", created_at="2026-09-28",
               updated_at="2026-09-28"), "info-2")
    backend.delete_request("info-1", "human", "reason", 1, "delete-1")
    assert deletion.approve_delete("info-1", "delete-1").status == "DELETED"
    assert backend.get("info-1") is None
    assert backend.get("info-2") is not None


def test_unreadable_thread_blocks_guarded_deletion(tmp_path):
    backend, threads, deletion = stores(tmp_path)
    backend.store(Memory("info-1"))
    backend.delete_request("info-1", "human", "reason", 1, "delete-1")
    (threads.threads_root / "broken.md").write_text("bad Thread")
    with pytest.raises(InformationDeletionBlocked, match="unreadable"):
        deletion.approve_delete("info-1", "delete-1")
    assert backend.get("info-1") is not None


def test_direct_backend_approval_cannot_bypass_link_guard(tmp_path):
    backend, threads, _ = stores(tmp_path)
    backend.store(Memory("info-1", content="keep"))
    ThreadInformationLinkService(backend, threads).create(
        Thread("thread-1", "Title", "Objective", created_at="2026-09-28",
               updated_at="2026-09-28"), "info-1")
    backend.delete_request("info-1", "human", "reason", 1, "delete-1")

    with pytest.raises(InformationDeletionBlocked, match="linked"):
        backend.approve_delete("info-1", "delete-1")
    assert backend.get("info-1").content == "keep"


@pytest.mark.parametrize("thread_file", ["invalid", "symlink"])
def test_direct_backend_approval_rejects_untrusted_thread(tmp_path, thread_file):
    backend, threads, _ = stores(tmp_path)
    backend.store(Memory("info-1", content="keep"))
    backend.delete_request("info-1", "human", "reason", 1, "delete-1")
    path = threads.threads_root / "thread-1.md"
    if thread_file == "symlink":
        target = tmp_path / "outside.md"
        target.write_text("outside")
        path.symlink_to(target)
    else:
        path.write_text("invalid Thread")

    with pytest.raises(InformationDeletionBlocked):
        backend.approve_delete("info-1", "delete-1")
    assert backend.get("info-1").content == "keep"
    request = json.loads((tmp_path / "history/pending-delete/info-1.json").read_text())
    assert request["status"] == "PENDING_DELETE"


@pytest.mark.parametrize("relation", [
    {"type": "CONCERNS"},
    {"type": "CONCERNS", "target_id": "info-2", "target": "info-1"},
])
def test_direct_backend_approval_rejects_ambiguous_concerns_relation(tmp_path, relation):
    backend, threads, _ = stores(tmp_path)
    backend.store(Memory("info-1", content="keep"))
    malformed = Thread("thread-1", "Title", "Objective", relations=[relation],
                       created_at="2026-09-28", updated_at="2026-09-28")
    # Existing malformed data can still be encountered even though the writer rejects it.
    threads._path("thread-1").write_text(threads._serialize(malformed))
    backend.delete_request("info-1", "human", "reason", 1, "delete-1")

    with pytest.raises(InformationDeletionBlocked, match="Thread CONCERNS target"):
        backend.approve_delete("info-1", "delete-1")
    assert backend.get("info-1").content == "keep"
    request = json.loads((tmp_path / "history/pending-delete/info-1.json").read_text())
    assert request["status"] == "PENDING_DELETE"
