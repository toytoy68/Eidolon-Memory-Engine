import json

import pytest

from core.backend.errors import InvalidMemory
from core.backend.filesystem import FilesystemBackend
from core.backend.models import Memory
from core.information.relation_audit import audit_relations, main


def test_relation_audit_counts_targets_without_inferring_external_type(tmp_path, capsys):
    backend = FilesystemBackend(tmp_path / "memory/persistent", tmp_path / "memory/history")
    backend.store(Memory("target", content="private target"))
    backend.store(Memory("source", content="private source", relations=[
        {"type": "RELATED_TO", "target_id": "target"},
        {"type": "CONCERNS", "target": "robot"},
        {"type": "RELATED_TO", "target": "source"},
        {"type": "RELATED_TO", "target_id": "target", "target": "robot"},
        {"type": "RELATED_TO"},
    ]))
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
