import json
from pathlib import Path

import pytest

from tools import vm_acceptance


def test_acceptance_uses_only_explicit_workdir_and_detects_source_change(tmp_path, monkeypatch):
    source = tmp_path / "source"
    (source / "memory/persistent").mkdir(parents=True)
    (source / "memory/persistent/info.md").write_bytes(b"original")
    workdir = tmp_path / "work"
    calls = []

    def runner(arguments, **kwargs):
        calls.append((arguments, kwargs))
        assert kwargs["env"]["TMPDIR"].startswith(str(workdir))
        assert kwargs["env"]["MEMORY_ENGINE_ROOT"].startswith(str(workdir))
        assert "--basetemp" in arguments
        return type("Result", (), {"returncode": 0, "stdout": "5 passed, 624 deselected", "stderr": ""})()

    monkeypatch.setattr(vm_acceptance.subprocess, "run", runner)
    monkeypatch.setattr(vm_acceptance, "inventory", lambda root: {"categories": {}, "needs_review": []})
    monkeypatch.setattr(vm_acceptance, "audit_relations", lambda *a, **kw: {"relations": {}})
    monkeypatch.setattr(vm_acceptance, "audit_lifecycle", lambda *a, **kw: {"count": 0})
    monkeypatch.setattr(vm_acceptance, "audit_deletions", lambda *a, **kw: {"issues": []})
    monkeypatch.setattr(vm_acceptance, "active_writers", lambda root: [])

    report = vm_acceptance.run(source, workdir, at="2026-09-30T00:00:00Z")

    assert len(calls) == 1
    assert [step["status"] for step in report["steps"]] == ["OK"] * 5
    assert (workdir / "vm-acceptance-report.json").is_file()
    assert json.loads((workdir / "vm-acceptance-report.json").read_text()) == report
    assert (source / "memory/persistent/info.md").read_bytes() == b"original"
    restored = workdir / "restored/memory/persistent/info.md"
    assert restored.read_bytes() == b"original"
    assert report["steps"][2]["details"]["files_verified"] >= 1


def test_acceptance_rejects_workdir_overlapping_source(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    with pytest.raises(ValueError, match="separate"):
        vm_acceptance.run(source, source / "work", at="2026-09-30T00:00:00Z")
    assert not (source / "work").exists()


def test_acceptance_reports_external_source_change(tmp_path, monkeypatch):
    source = tmp_path / "source"
    source.mkdir()
    (source / "datum").write_text("before")
    monkeypatch.setattr(vm_acceptance, "inventory", lambda root: {"needs_review": []})
    monkeypatch.setattr(vm_acceptance, "active_writers", lambda root: [])
    monkeypatch.setattr(vm_acceptance, "audit_relations", lambda *a, **kw: {})
    monkeypatch.setattr(vm_acceptance, "audit_lifecycle", lambda *a, **kw: {})
    monkeypatch.setattr(vm_acceptance, "audit_deletions", lambda *a, **kw: {"issues": []})

    def external_change(*args, **kwargs):
        (source / "datum").write_text("changed")
        return type("Result", (), {"returncode": 0, "stdout": "5 passed", "stderr": ""})()

    monkeypatch.setattr(vm_acceptance.subprocess, "run", external_change)
    report = vm_acceptance.run(source, tmp_path / "work", at="2026-09-30T00:00:00Z")
    assert report["status"] == "KO"
    assert report["steps"][-1]["name"] == "source_unchanged"
