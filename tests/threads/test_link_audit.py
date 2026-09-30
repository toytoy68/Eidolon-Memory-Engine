import json
import pytest

from core.backend.filesystem import FilesystemBackend
from core.backend.models import Memory
from core.threads.link_audit import audit_links, main
from core.threads.link_service import ThreadInformationLinkService
from core.threads.models import Thread
from core.threads.storage import ThreadStorage


def test_audit_reports_orphan_after_information_deletion(tmp_path, capsys):
    root = tmp_path / "memory"
    backend = FilesystemBackend(root / "persistent", root / "history")
    storage = ThreadStorage(root / "persistent")
    backend.store(Memory("info-1", content="private content"))
    ThreadInformationLinkService(backend, storage).create(
        Thread("thread-1", "Title", "Objective", created_at="2026-09-28",
               updated_at="2026-09-28"), "info-1")

    assert audit_links(tmp_path) == {"threads_checked": 1, "links_checked": 1, "issues": []}
    # Simulate a legacy writer or damaged copy bypassing the guarded backend.
    backend._path("info-1").unlink()

    assert main(["--root", str(tmp_path)]) == 1
    report = json.loads(capsys.readouterr().out)
    assert report["issues"] == [{
        "thread": "memory/persistent/threads/thread-1.md",
        "reason": "missing_information",
    }]
    assert "private content" not in str(report)


def test_audit_flags_invalid_thread_without_writing(tmp_path):
    root = tmp_path / "memory/persistent/threads"
    root.mkdir(parents=True)
    path = root / "bad.md"
    path.write_text("corrupt")
    assert audit_links(tmp_path)["issues"] == [{
        "thread": "memory/persistent/threads/bad.md", "reason": "invalid_thread",
    }]
    assert path.read_text() == "corrupt"
    assert not (root / ".write.lock").exists()


def test_audit_flags_ambiguous_concerns_target(tmp_path):
    root = tmp_path / "memory"
    threads = ThreadStorage(root / "persistent")
    malformed = Thread("thread-1", "Title", "Objective", created_at="2026-09-28",
                       updated_at="2026-09-28", relations=[
                           {"type": "CONCERNS", "target_id": "info-2", "target": "info-1"},
                       ])
    # Simulate historical data bypassing the current storage writer.
    threads._path("thread-1").write_text(threads._serialize(malformed))
    assert audit_links(tmp_path) == {"threads_checked": 1, "links_checked": 1, "issues": [{
        "thread": "memory/persistent/threads/thread-1.md", "reason": "invalid_target_id",
    }]}


def test_audit_rejects_symlinked_engine_ancestor(tmp_path):
    actual = tmp_path / "actual"
    threads = actual / "engine/memory/persistent/threads"
    threads.mkdir(parents=True)
    (threads / "private.md").write_text("private thread")
    (tmp_path / "linked").symlink_to(actual, target_is_directory=True)

    with pytest.raises(ValueError, match="symlinked directory"):
        audit_links(tmp_path / "linked/engine")
    assert (threads / "private.md").read_text() == "private thread"


def test_audit_skips_symlinked_memory_directory(tmp_path):
    external = tmp_path / "external"
    threads = external / "persistent/threads"
    threads.mkdir(parents=True)
    (threads / "private.md").write_text("private thread")
    root = tmp_path / "engine"
    root.mkdir()
    (root / "memory").symlink_to(external, target_is_directory=True)

    assert audit_links(root) == {"threads_checked": 0, "links_checked": 0, "issues": [{
        "thread": "memory/persistent/threads", "reason": "symlink_skipped",
    }]}
    assert (threads / "private.md").read_text() == "private thread"
