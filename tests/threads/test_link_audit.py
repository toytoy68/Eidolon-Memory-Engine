import json

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
