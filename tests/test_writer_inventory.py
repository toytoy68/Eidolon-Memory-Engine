"""Inventory is a clue for the VM operator, including idle service units."""

import json
from pathlib import Path

import pytest

from tools.writer_inventory import discover_writers


def test_inventory_finds_running_and_configured_writers_without_revealing_arguments(tmp_path):
    proc = tmp_path / "proc"
    (proc / "101").mkdir(parents=True)
    (proc / "101/cmdline").write_bytes(
        b"/usr/bin/python3\0/opt/eidolon-memory-engine/services/memory-controller/memory_controller.py\0"
        b"--token=PRIVATE\0")
    (proc / "102").mkdir()
    (proc / "102/cmdline").write_bytes(b"/usr/bin/python3\0unrelated.py\0")
    units = tmp_path / "units"
    units.mkdir()
    (units / "memory-writer.service").write_text(
        "[Service]\nExecStart=/usr/bin/python3 /opt/eidolon-memory-engine/services/memory-controller/memory_controller.py\n")
    cron = tmp_path / "cron"
    cron.write_text("@hourly /opt/eidolon-memory-engine/services/memory-relations/eidolon-memory-relations\n")
    before = {path: path.read_bytes() for path in (proc / "101/cmdline", proc / "102/cmdline",
                                                  units / "memory-writer.service", cron)}

    result = discover_writers(proc_root=proc, unit_dirs=(units,), cron_paths=(cron,))

    assert result["running"] == [{"pid": 101, "marker": "memory_controller.py"}]
    assert result["configured"] == [
        {"path": str(cron), "marker": "eidolon-memory-relations"},
        {"path": str(units / "memory-writer.service"), "marker": "memory_controller.py"},
    ]
    assert "PRIVATE" not in str(result)
    assert all(path.read_bytes() == content for path, content in before.items())


def test_inventory_does_not_claim_an_empty_scan_proves_no_writers(tmp_path):
    result = discover_writers(proc_root=tmp_path / "missing",
                              unit_dirs=(tmp_path / "no-units",), cron_paths=())
    assert result["running"] == result["configured"] == []
    assert result["coverage"] == "heuristic_manual_service_review_required"


@pytest.mark.parametrize('scan_error', [PermissionError, OSError])
def test_unreadable_cron_directory_is_reported_and_other_sources_survive(tmp_path, monkeypatch, scan_error):
    proc = tmp_path / 'proc'
    (proc / '101').mkdir(parents=True)
    (proc / '101/cmdline').write_bytes(b'python\0memory_controller.py\0--token=PRIVATE')
    denied = tmp_path / 'cron-private'; denied.mkdir()
    readable = tmp_path / 'cron-readable'; readable.mkdir()
    job = readable / 'memory-job'
    job.write_text('@hourly eidolon-memory-relations --token=PRIVATE\n')
    original = Path.iterdir
    def guarded(path):
        if path == denied:
            raise scan_error('directory inaccessible')
        return original(path)
    monkeypatch.setattr(Path, 'iterdir', guarded)
    result = discover_writers(proc_root=proc, unit_dirs=(), cron_paths=(denied, readable))
    assert result['unreadable'] == [str(denied)]
    assert result['running'] == [{'pid': 101, 'marker': 'memory_controller.py'}]
    assert result['configured'] == [{'path': str(job), 'marker': 'eidolon-memory-relations'}]
    assert result['coverage'] == 'heuristic_manual_service_review_required'
    assert 'PRIVATE' not in str(result)
    assert job.read_text() == '@hourly eidolon-memory-relations --token=PRIVATE\n'


def test_cli_emits_partial_inventory_when_cron_directory_is_protected(tmp_path, monkeypatch, capsys):
    import tools.writer_inventory as module
    denied = tmp_path / 'cron-private'; denied.mkdir()
    original = Path.iterdir
    def guarded(path):
        if path == denied:
            raise PermissionError('directory inaccessible')
        return original(path)
    monkeypatch.setattr(Path, 'iterdir', guarded)
    monkeypatch.setattr(module, 'discover_writers', lambda: discover_writers(
        proc_root=tmp_path / 'missing', unit_dirs=(), cron_paths=(denied,)))
    assert module.main([]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result['unreadable'] == [str(denied)]
    assert result['coverage'] == 'heuristic_manual_service_review_required'
