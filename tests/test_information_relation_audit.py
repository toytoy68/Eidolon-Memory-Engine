import json

import pytest

from core.backend.errors import InvalidMemory
from core.backend.filesystem import FilesystemBackend
from core.backend.models import Memory
from core.information.relation_audit import audit_relations, main


def test_relation_audit_counts_targets_without_inferring_external_type(tmp_path, capsys):
    backend = FilesystemBackend(tmp_path / "memory/persistent", tmp_path / "memory/history")
    backend.store(Memory("target", content="private target"))
    legacy_source = Memory("source", content="private source", relations=[
        {"type": "RELATED_TO", "target_id": "target"},
        {"type": "CONCERNS", "target": "robot"},
        {"type": "RELATED_TO", "target": "source"},
        {"type": "RELATED_TO", "target_id": "target", "target": "robot"},
        {"type": "RELATED_TO"},
    ])
    backend._path("source").write_text(backend._serialize(legacy_source))
    before = {path: path.read_bytes() for path in tmp_path.rglob("*") if path.is_file()}
    assert main(["--root", str(tmp_path)]) == 0
    output = capsys.readouterr().out
    assert json.loads(output)["relations"] == {
        "information_target": 1, "external_or_missing": 1,
        "self": 1, "ambiguous": 1, "invalid": 1,
    }
    assert "private" not in output and "robot" not in output
    assert {path: path.read_bytes() for path in tmp_path.rglob("*") if path.is_file()} == before


def test_relation_audit_rejects_invalid_source(tmp_path):
    persistent = tmp_path / "persistent"
    persistent.mkdir()
    (persistent / "bad.md").write_text("private malformed")
    with pytest.raises(InvalidMemory):
        audit_relations(persistent)


def test_relation_audit_distinguishes_deleted_identity_from_external_target(tmp_path, capsys):
    backend = FilesystemBackend(tmp_path / "memory/persistent", tmp_path / "memory/history")
    backend.store(Memory("target", content="private"))
    backend.delete_request("target", "human", "obsolete", 1, "delete-target")
    backend.approve_delete("target", "delete-target")
    # A historical writer may have bypassed the backend after the deletion.
    source = Memory("source", relations=[
        {"type": "RELATED_TO", "target_id": "target"},
        {"type": "RELATED_TO", "target_id": "robot"},
    ])
    backend._path("source").write_text(backend._serialize(source))
    before = {path: path.read_bytes() for path in tmp_path.rglob("*") if path.is_file()}
    assert main(["--root", str(tmp_path)]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["relations"] == {"external_or_missing": 1,
                                   "reserved_information_target": 1}
    assert '"target"' not in json.dumps(report) and "private" not in json.dumps(report)
    assert {path: path.read_bytes() for path in tmp_path.rglob("*") if path.is_file()} == before


def test_relation_audit_refuses_linked_or_invalid_receipt(tmp_path):
    backend = FilesystemBackend(tmp_path / "memory/persistent", tmp_path / "memory/history")
    backend.store(Memory("source", relations=[{"type": "RELATED_TO", "target_id": "missing"}]))
    receipt = backend.pending_delete_root / "missing.json"
    receipt.write_text("{bad", encoding="utf-8")
    with pytest.raises(InvalidMemory):
        audit_relations(backend.persistent_root, history_root=backend.history_root)
    receipt.unlink()
    receipt.symlink_to(tmp_path / "outside.json")
    with pytest.raises(InvalidMemory):
        audit_relations(backend.persistent_root, history_root=backend.history_root)


def test_relation_audit_refuses_receipt_directory_replaced_by_file(tmp_path):
    persistent = tmp_path / "memory/persistent"
    persistent.mkdir(parents=True)
    history = tmp_path / "memory/history"
    history.mkdir()
    (history / "pending-delete").write_text("damaged")

    with pytest.raises(InvalidMemory, match="not a directory"):
        audit_relations(persistent, history_root=history)
