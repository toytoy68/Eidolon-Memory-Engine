import importlib.util
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Event

import pytest

from core.migration.legacy_guard import require_legacy_persistent_only
from core.persistence import exclusive_write


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


def test_controller_working_update_waits_for_shared_writer_lock(tmp_path, monkeypatch):
    controller = load_controller()
    working = tmp_path / "working"
    working.mkdir()
    source = working / "info-1.md"
    source.write_text("legacy")
    monkeypatch.setattr(controller, "WORKING_ROOT", working)
    entered = Event()
    started = Event()
    monkeypatch.setattr(controller, "_update_information_unlocked", lambda *args: entered.set() or 0)

    def update():
        started.set()
        return controller.update_information(source, None, None, None, None, "reason", "UPDATED")

    with ThreadPoolExecutor(max_workers=1) as executor:
        with exclusive_write(working):
            future = executor.submit(update)
            assert started.wait(1)
            assert not entered.is_set()
        assert future.result(timeout=2) == 0
    assert entered.is_set()


def test_controller_rejects_updates_outside_memory_roots(tmp_path, monkeypatch):
    controller = load_controller()
    monkeypatch.setattr(controller, "WORKING_ROOT", tmp_path / "working")
    monkeypatch.setattr(controller, "PERSISTENT_ROOT", tmp_path / "persistent")
    outside = tmp_path / "outside.md"
    outside.write_text("private")
    assert controller.update_information(outside, None, None, None, None, "reason", "UPDATED") == 1
    assert outside.read_text() == "private"


def test_legacy_guard_rejects_linked_parent_before_scanning(tmp_path):
    outside = tmp_path / "outside"
    (outside / "persistent").mkdir(parents=True)
    (outside / "persistent/private.md").write_text("private")
    linked = tmp_path / "memory"
    linked.symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValueError, match="symlink"):
        require_legacy_persistent_only(linked / "persistent", tmp_path / "history")
    assert (outside / "persistent/private.md").read_text() == "private"


def test_legacy_guard_rejects_linked_journal_parent(tmp_path):
    persistent = tmp_path / "persistent"
    persistent.mkdir()
    history = tmp_path / "history"
    history.mkdir()
    outside = tmp_path / "external-operations"
    (outside / "thread-create-v1").mkdir(parents=True)
    (history / "operations").symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValueError, match="journal"):
        require_legacy_persistent_only(persistent, history)


def test_legacy_guard_blocks_orphan_core_event_journal(tmp_path):
    persistent = tmp_path / "persistent"
    persistent.mkdir()
    history = tmp_path / "history"
    events = history / "events/thread-create-v1"
    events.mkdir(parents=True)
    (events / "event.md").write_text("core Event")
    with pytest.raises(ValueError, match="journal"):
        require_legacy_persistent_only(persistent, history)
