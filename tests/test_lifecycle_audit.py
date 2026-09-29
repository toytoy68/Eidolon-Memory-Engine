import json

import pytest

from core.backend.filesystem import FilesystemBackend
from core.backend.models import Memory
from core.information.lifecycle_audit import audit_lifecycle, main


def test_lifecycle_audit_separates_retention_from_validity(tmp_path, capsys):
    backend = FilesystemBackend(tmp_path / "memory/persistent", tmp_path / "memory/history")
    backend.store(Memory("old", content="private history",
                         metadata={"retention": "PERMANENT"},
                         temporal={"valid_until": "2026-09-01T00:00:00+02:00"}))
    backend.store(Memory("temporary", content="private current",
                         metadata={"retention": "TEMPORARY"},
                         temporal={"valid_until": "2026-10-01T00:00:00+02:00"}))
    backend.store(Memory("unknown", content="private unknown"))
    backend.store(Memory("invalid", content="private invalid",
                         metadata={"retention": "UNRECOGNIZED"},
                         temporal={"valid_until": "yesterday"}))
    before = {path: path.read_bytes() for path in tmp_path.rglob("*") if path.is_file()}
    assert main(["--root", str(tmp_path), "--at", "2026-09-29T12:00:00+02:00"]) == 0
    output = capsys.readouterr().out
    report = json.loads(output)
    assert report["retention"] == {
        "PERMANENT": 1, "TEMPORARY": 1, "invalid": 1, "missing": 1,
    }
    assert report["applicability"] == {
        "ended": 1, "not_ended": 1, "invalid": 1, "unknown": 1,
    }
    assert report["policy"] == "read_only_no_deletion_inferred"
    assert "private" not in output and "old" not in output
    assert {path: path.read_bytes() for path in tmp_path.rglob("*") if path.is_file()} == before


def test_lifecycle_audit_requires_timezone_aware_instant(tmp_path):
    persistent = tmp_path / "memory/persistent"
    persistent.mkdir(parents=True)
    with pytest.raises(ValueError, match="timezone"):
        audit_lifecycle(persistent, as_of="2026-09-29T12:00:00")


def test_lifecycle_audit_refuses_linked_memory_parent(tmp_path):
    outside = tmp_path / "outside"
    (outside / "persistent").mkdir(parents=True)
    (tmp_path / "memory").symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValueError, match="symlinked"):
        audit_lifecycle(tmp_path / "memory/persistent", as_of="2026-09-29T12:00:00Z")
