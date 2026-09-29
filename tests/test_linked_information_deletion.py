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


def test_information_relation_blocks_delete_until_source_is_updated(tmp_path):
    backend, _, _ = stores(tmp_path)
    backend.store(Memory("target", content="keep"))
    backend.store(Memory("source", content="related",
                         relations=[{"type": "RELATED_TO", "target_id": "target"}]))
    backend.delete_request("target", "human", "obsolete", 1, "delete-target")
    with pytest.raises(InformationDeletionBlocked, match="referenced by Information"):
        backend.approve_delete("target", "delete-target")
    assert backend.get("target").content == "keep"
    receipt = json.loads((backend.pending_delete_root / "target.json").read_text())
    assert receipt["status"] == "PENDING_DELETE"
    backend.update("source", Memory("source", content="related", relations=[]),
                   previous_revision=1)
    assert backend.approve_delete("target", "delete-target").status == "DELETED"


def test_unreadable_information_blocks_other_information_deletion(tmp_path):
    backend, _, _ = stores(tmp_path)
    backend.store(Memory("target"))
    backend.delete_request("target", "human", "reason", 1, "delete-target")
    (backend.persistent_root / "broken.md").write_text("invalid Information")
    with pytest.raises(InformationDeletionBlocked, match="unreadable Information"):
        backend.approve_delete("target", "delete-target")
    assert backend.get("target") is not None


@pytest.mark.parametrize("relation", [
    {"type": "RELATED_TO", "target": "target"},
    {"type": "RELATED_TO", "target_id": "other", "target": "target"},
    {"type": "RELATED_TO"},
])
def test_information_relation_aliases_or_ambiguity_block_delete(tmp_path, relation):
    backend, _, _ = stores(tmp_path)
    backend.store(Memory("target"))
    backend.store(Memory("source", relations=[relation]))
    backend.delete_request("target", "human", "reason", 1, "delete-target")
    with pytest.raises(InformationDeletionBlocked):
        backend.approve_delete("target", "delete-target")
    assert backend.get("target") is not None


def test_symlinked_information_source_blocks_delete(tmp_path):
    backend, _, _ = stores(tmp_path)
    backend.store(Memory("target"))
    backend.delete_request("target", "human", "reason", 1, "delete-target")
    outside = tmp_path / "outside.md"
    outside.write_text("private")
    (backend.persistent_root / "source.md").symlink_to(outside)
    with pytest.raises(InformationDeletionBlocked, match="symlink"):
        backend.approve_delete("target", "delete-target")
    assert outside.read_text() == "private"


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
