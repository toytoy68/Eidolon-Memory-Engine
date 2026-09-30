import json
from pathlib import Path

import pytest

from tools import vm_acceptance
from tools.generate_scenario import generate


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
    monkeypatch.setattr(vm_acceptance, "audit_lifecycle", lambda *a, **kw: {
        "count": 0, "retention": {}, "applicability": {}, "epistemic_by_applicability": {}})
    monkeypatch.setattr(vm_acceptance, "audit_deletions", lambda *a, **kw: {"issues": []})
    monkeypatch.setattr(vm_acceptance, "active_writers", lambda root: [])
    monkeypatch.setattr(vm_acceptance, "discover_writers", lambda: {
        "running": [], "configured": [], "unreadable": [], "coverage": "heuristic_manual_service_review_required"})

    report = vm_acceptance.run(source, workdir, at="2026-09-30T00:00:00Z")

    assert len(calls) == 1
    assert len(report["versions"]["engine_commit"]) == 40
    assert [step["status"] for step in report["steps"]] == ["OK"] * 7
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
    monkeypatch.setattr(vm_acceptance, "discover_writers", lambda: {
        "running": [], "configured": [], "unreadable": [], "coverage": "heuristic_manual_service_review_required"})
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


def test_acceptance_flags_invalid_relation_and_lifecycle_counts(tmp_path, monkeypatch):
    source = tmp_path / "source"
    source.mkdir()
    (source / "datum").write_text("before")
    monkeypatch.setattr(vm_acceptance, "inventory", lambda root: {"needs_review": []})
    monkeypatch.setattr(vm_acceptance, "active_writers", lambda root: [])
    monkeypatch.setattr(vm_acceptance, "discover_writers", lambda: {
        "running": [], "configured": [], "unreadable": [], "coverage": "heuristic_manual_service_review_required"})
    monkeypatch.setattr(vm_acceptance, "audit_relations", lambda *a, **kw: {
        "relations": {"invalid": 2, "external_or_missing": 1}})
    monkeypatch.setattr(vm_acceptance, "audit_lifecycle", lambda *a, **kw: {
        "retention": {"invalid": 1}, "applicability": {"invalid": 1},
        "epistemic_by_applicability": {"invalid": {"unknown": 1}}})
    monkeypatch.setattr(vm_acceptance, "audit_deletions", lambda *a, **kw: {"issues": []})
    monkeypatch.setattr(vm_acceptance.subprocess, "run", lambda *a, **kw: type(
        "Result", (), {"returncode": 0, "stdout": "5 passed", "stderr": ""})())

    result = vm_acceptance.run(source, tmp_path / "work", at="2026-09-30T00:00:00Z")

    steps = {item["name"]: item for item in result["steps"]}
    assert steps["audit_relations"]["status"] == "KO"
    assert steps["audit_relations"]["details"]["relations"]["invalid"] == 2
    assert steps["audit_lifecycle"]["status"] == "KO"
    assert steps["audit_deletions"]["status"] == "OK"
    assert result["status"] == "KO"


def test_acceptance_reports_idle_unit_and_flags_active_writer(tmp_path, monkeypatch):
    source = tmp_path / "source"
    source.mkdir()
    monkeypatch.setattr(vm_acceptance, "inventory", lambda root: {"needs_review": []})
    monkeypatch.setattr(vm_acceptance, "active_writers", lambda root: [])
    monkeypatch.setattr(vm_acceptance, "discover_writers", lambda: {
        "running": [{"pid": 123, "marker": "memory_controller.py"}],
        "configured": [{"path": "/etc/systemd/system/memory.service", "marker": "memory_controller.py"}],
        "unreadable": [], "coverage": "heuristic_manual_service_review_required"})
    monkeypatch.setattr(vm_acceptance, "audit_relations", lambda *a, **kw: {"relations": {}})
    monkeypatch.setattr(vm_acceptance, "audit_lifecycle", lambda *a, **kw: {
        "retention": {}, "applicability": {}, "epistemic_by_applicability": {}})
    monkeypatch.setattr(vm_acceptance, "audit_deletions", lambda *a, **kw: {"issues": []})
    monkeypatch.setattr(vm_acceptance.subprocess, "run", lambda *a, **kw: type(
        "Result", (), {"returncode": 0, "stdout": "5 passed", "stderr": ""})())

    report = vm_acceptance.run(source, tmp_path / "work", at="2026-09-30T00:00:00Z")

    assert report["status"] == "KO"
    writers = report["steps"][0]
    assert writers["status"] == "KO"
    assert writers["details"]["system_writers"]["configured"][0]["path"].endswith("memory.service")
    assert writers["details"]["system_writers"]["running"][0]["pid"] == 123


def test_acceptance_keeps_format_evidence_when_inventory_fails(tmp_path, monkeypatch):
    source = tmp_path / "source"
    source.mkdir()
    monkeypatch.setattr(vm_acceptance, "active_writers", lambda root: [])
    monkeypatch.setattr(vm_acceptance, "discover_writers", lambda: {
        "running": [], "configured": [], "unreadable": [], "coverage": "heuristic_manual_service_review_required"})
    monkeypatch.setattr(vm_acceptance, "inventory", lambda root: {
        "needs_review": [{"path": "memory/history/events/broken.md", "reason": "unknown_format"}]})
    monkeypatch.setattr(vm_acceptance, "audit_relations", lambda *a, **kw: {"relations": {}})
    monkeypatch.setattr(vm_acceptance, "audit_lifecycle", lambda *a, **kw: {
        "retention": {}, "applicability": {}, "epistemic_by_applicability": {}})
    monkeypatch.setattr(vm_acceptance, "audit_deletions", lambda *a, **kw: {"issues": []})
    monkeypatch.setattr(vm_acceptance.subprocess, "run", lambda *a, **kw: type(
        "Result", (), {"returncode": 0, "stdout": "5 passed", "stderr": ""})())

    result = vm_acceptance.run(source, tmp_path / "work", at="2026-09-30T00:00:00Z")

    assert result["steps"][1]["status"] == "KO"
    assert result["steps"][1]["details"]["needs_review"][0]["path"] == (
        "memory/history/events/broken.md")


def test_acceptance_real_audits_on_generated_stopped_copy(tmp_path, monkeypatch):
    generate(tmp_path / "scenario", count=50)
    source = tmp_path / "scenario/core"
    original = vm_acceptance.hashes(source)
    monkeypatch.setattr(vm_acceptance, "active_writers", lambda root: [])
    monkeypatch.setattr(vm_acceptance, "discover_writers", lambda: {
        "running": [], "configured": [], "unreadable": [], "coverage": "heuristic_manual_service_review_required"})
    monkeypatch.setattr(vm_acceptance.subprocess, "run", lambda *a, **kw: type(
        "Result", (), {"returncode": 0, "stdout": "5 passed", "stderr": ""})())

    report = vm_acceptance.run(source, tmp_path / "acceptance", at="2026-09-30T00:00:00Z")

    steps = {item["name"]: item for item in report["steps"]}
    assert steps["backup_restore"]["status"] == "OK"
    assert steps["audit_relations"]["status"] == "OK"
    assert steps["audit_lifecycle"]["status"] == "OK"
    assert steps["audit_deletions"]["status"] == "KO"
    assert any(item["reason"] == "deletion_requires_resume"
               for item in steps["audit_deletions"]["details"]["issues"])
    assert vm_acceptance.hashes(source) == original
    assert vm_acceptance.hashes(tmp_path / "acceptance/restored") == original
