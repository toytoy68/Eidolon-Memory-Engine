import importlib.util
from pathlib import Path

import pytest

from core.migration.legacy_guard import require_legacy_persistent_only


CONTROLLER = Path(__file__).resolve().parents[1] / "services/memory-controller/memory_controller.py"


def load_controller():
    spec = importlib.util.spec_from_file_location("legacy_controller_for_test", CONTROLLER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_legacy_guard_accepts_historical_files_and_blocks_core(tmp_path):
    persistent = tmp_path / "persistent"
    history = tmp_path / "history"
    persistent.mkdir()
    (persistent / "old.md").write_text("---\nid: old\n---\n# Content\n")
    require_legacy_persistent_only(persistent, history)
    (persistent / "new.md").write_text("# Eidolon Information Object\n\nVersion: 0.2\n")
    with pytest.raises(ValueError, match="core Information"):
        require_legacy_persistent_only(persistent, history)


def test_legacy_guard_blocks_core_thread_or_journal(tmp_path):
    persistent = tmp_path / "persistent"
    history = tmp_path / "history"
    persistent.mkdir()
    threads = persistent / "threads"
    threads.mkdir()
    (threads / "thread.md").write_text("core")
    with pytest.raises(ValueError, match="Thread"):
        require_legacy_persistent_only(persistent, history)
    (threads / "thread.md").unlink()
    journal = history / "operations/thread-create-v1"
    journal.mkdir(parents=True)
    (journal / "op.json").write_text("{}")
    with pytest.raises(ValueError, match="journal"):
        require_legacy_persistent_only(persistent, history)


def test_controller_blocks_execution_before_legacy_writer_runs(tmp_path, monkeypatch):
    controller = load_controller()
    persistent = tmp_path / "persistent"
    persistent.mkdir()
    (persistent / "core.md").write_text("# Eidolon Information Object\n\nVersion: 0.2\n")
    monkeypatch.setattr(controller, "PERSISTENT_ROOT", persistent)
    monkeypatch.setattr(controller, "HISTORY_ROOT", tmp_path / "history")
    monkeypatch.setattr(controller, "_execute_execution_plan_unlocked", lambda _: pytest.fail("wrote"))
    result = controller.execute_execution_plan({"operation_id": "op", "input": {"information_id": "old"}})
    assert result["result"] == "BLOCK"
    assert result["writes_performed"] is False
    assert "core Information" in result["reason"]


def test_controller_blocks_direct_persistent_update_when_core_present(tmp_path, monkeypatch):
    controller = load_controller()
    persistent = tmp_path / "persistent"
    persistent.mkdir()
    old = persistent / "old.md"
    old.write_text("---\nid: old\n---\noriginal\n")
    (persistent / "core.md").write_text("# Eidolon Information Object\n\nVersion: 0.2\n")
    monkeypatch.setattr(controller, "PERSISTENT_ROOT", persistent)
    monkeypatch.setattr(controller, "HISTORY_ROOT", tmp_path / "history")
    monkeypatch.setattr(controller, "_update_information_unlocked", lambda *args: pytest.fail("wrote"))
    assert controller.update_information(old, None, None, None, None, "reason", "UPDATED") == 1
    assert old.read_text().endswith("original\n")
