"""Inventory is a clue for the VM operator, including idle service units."""

from pathlib import Path

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
