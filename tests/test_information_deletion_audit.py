import json

import pytest

from core.backend.filesystem import FilesystemBackend
from core.backend.errors import InvalidMemory
from core.backend.models import Memory
from core.information.deletion_audit import audit_deletions, main


def test_audit_reports_deletion_waiting_for_resume(tmp_path):
    root = tmp_path
    requests = root / "memory/history/pending-delete"
    requests.mkdir(parents=True)
    (requests / "info-1.json").write_text(json.dumps({
        "information_id": "info-1", "operation_id": "op-1", "revision": 1,
        "status": "APPLYING_DELETE", "content_sha256": "a" * 64,
        "requested_by": "human", "reason": "test",
    }))
    report = audit_deletions(root)
    assert report["requests_checked"] == 1
    assert report["issues"][0]["reason"] == "deletion_requires_resume"


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


@pytest.mark.parametrize("field,value", [("revision", 0), ("operation_id", "")])
def test_audit_rejects_unusable_request_identifiers(tmp_path, field, value):
    store = backend(tmp_path)
    store.store(Memory("info-1"))
    store.delete_request("info-1", "human", "reason", 1, "op-1")
    request = tmp_path / "memory/history/pending-delete/info-1.json"
    record = json.loads(request.read_text())
    record[field] = value
    request.write_text(json.dumps(record))
    before = request.read_bytes()

    assert audit_deletions(tmp_path) == {"requests_checked": 0, "issues": [{
        "request": "memory/history/pending-delete/info-1.json",
        "reason": "invalid_request",
    }]}
    assert request.read_bytes() == before


def test_audit_reports_actual_symlinked_directory(tmp_path):
    (tmp_path / "memory/history/pending-delete").mkdir(parents=True)
    (tmp_path / "memory/persistent").symlink_to(tmp_path / "outside")
    assert audit_deletions(tmp_path) == {"requests_checked": 0, "issues": [{
        "request": "memory/persistent", "reason": "symlink_skipped",
    }]}


@pytest.mark.parametrize("component", ["memory", "memory/history"])
def test_audit_does_not_follow_symlinked_parent_directory(tmp_path, component):
    external = tmp_path / "external"
    external.mkdir()
    parent = tmp_path / component
    parent.parent.mkdir(parents=True, exist_ok=True)
    parent.symlink_to(external, target_is_directory=True)
    report = audit_deletions(tmp_path)
    assert {"request": component, "reason": "symlink_skipped"} in report["issues"]
    assert report["requests_checked"] == 0


def test_audit_rejects_symlink_above_engine_root(tmp_path):
    external = tmp_path / "external"
    (external / "engine/memory/history/pending-delete").mkdir(parents=True)
    linked = tmp_path / "linked"
    linked.symlink_to(external, target_is_directory=True)
    assert audit_deletions(linked / "engine") == {"requests_checked": 0, "issues": [
        {"request": ".", "reason": "symlink_skipped"},
    ]}


@pytest.mark.parametrize("extra", ['"status":"DELETED"', '"revision":NaN'])
def test_audit_and_backend_reject_ambiguous_delete_receipt(tmp_path, extra):
    store = backend(tmp_path)
    store.store(Memory("info-1", content="private"))
    store.delete_request("info-1", "human", "reason", 1, "op-1")
    request = tmp_path / "memory/history/pending-delete/info-1.json"
    request.write_text(request.read_text().rstrip()[:-1] + "," + extra + "}")
    original = request.read_bytes()
    assert audit_deletions(tmp_path) == {"requests_checked": 0, "issues": [{
        "request": "memory/history/pending-delete/info-1.json", "reason": "invalid_request",
    }]}
    with pytest.raises(InvalidMemory):
        store.approve_delete("info-1", "op-1")
    assert request.read_bytes() == original
    assert store.get("info-1").content == "private"


@pytest.mark.parametrize("extra", [
    {"unexpected": "not preserved on rewrite"},
    {"content_sha256": "a" * 64},
])
def test_audit_and_backend_reject_unexpected_pending_receipt_fields(tmp_path, extra):
    store = backend(tmp_path)
    store.store(Memory("info-1", content="private"))
    store.delete_request("info-1", "human", "reason", 1, "op-1")
    request = tmp_path / "memory/history/pending-delete/info-1.json"
    request.write_text(json.dumps({**json.loads(request.read_text()), **extra}))
    original = request.read_bytes()

    assert audit_deletions(tmp_path)["issues"][0]["reason"] == "invalid_request"
    with pytest.raises(InvalidMemory):
        store.approve_delete("info-1", "op-1")
    assert request.read_bytes() == original
    assert store.get("info-1").content == "private"


def test_audit_reports_cancelled_request_without_information(tmp_path):
    store = backend(tmp_path)
    store.store(Memory("info-1"))
    store.delete_request("info-1", "human", "mistake", 1, "op-1")
    store.cancel_delete("info-1", "op-1")
    (store.persistent_root / "info-1.md").unlink()  # historical/foreign writer
    assert audit_deletions(tmp_path) == {"requests_checked": 1, "issues": [{
        "request": "memory/history/pending-delete/info-1.json",
        "reason": "cancelled_without_information",
    }]}
