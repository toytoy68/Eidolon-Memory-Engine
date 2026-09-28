import json

from core.backend.filesystem import FilesystemBackend
from core.backend.models import Memory
from core.information.deletion_audit import audit_deletions, main


def backend(root):
    return FilesystemBackend(root / "memory/persistent", root / "memory/history")


def test_audit_detects_interrupted_deletion_without_modifying_request(tmp_path, capsys):
    store = backend(tmp_path)
    store.store(Memory("info-1", content="private content"))
    store.delete_request("info-1", "human", "reason", 1, "op-1")
    request = tmp_path / "memory/history/pending-delete/info-1.json"
    before = request.read_bytes()
    (tmp_path / "memory/persistent/info-1.md").unlink()

    assert main(["--root", str(tmp_path)]) == 1
    report = json.loads(capsys.readouterr().out)
    assert report == {"requests_checked": 1, "issues": [{
        "request": "memory/history/pending-delete/info-1.json",
        "reason": "pending_without_information",
    }]}
    assert request.read_bytes() == before
    assert "private content" not in str(report)


def test_audit_accepts_completed_deletion_and_flags_malformed_record(tmp_path):
    store = backend(tmp_path)
    store.store(Memory("info-1"))
    store.delete_request("info-1", "human", "reason", 1, "op-1")
    store.approve_delete("info-1", "op-1")
    requests = tmp_path / "memory/history/pending-delete"
    (requests / "broken.json").write_text("[]")

    assert audit_deletions(tmp_path) == {"requests_checked": 1, "issues": [{
        "request": "memory/history/pending-delete/broken.json",
        "reason": "invalid_request",
    }]}
