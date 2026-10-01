"""Startup decisions must reflect persistent state, including omitted families."""
from dataclasses import replace
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from core.backend.filesystem import FilesystemBackend
from core.backend.models import Memory
from core.events.filesystem import FilesystemEventRepository
from core.information.writes import FilesystemInformationWrites
from core.migration.inventory import inventory
from core.operations.filesystem import FilesystemOperationRepository
from core.operations.models import OperationStatus
from core.operations.readiness import check_readiness, recover_all
from core.operations.thread_create import FilesystemLinkedThreadCreation
from core.operations.thread_delete import FilesystemThreadDeletion
from core.operations.thread_status import FilesystemThreadOperations
from core.threads.models import Thread, ThreadStatus
from core.threads.storage import ThreadStorage
from tools.vm_acceptance import hashes


def prepared(root, family, monkeypatch):
    persistent, history = root / "memory/persistent", root / "memory/history"
    backend = FilesystemBackend(persistent, history)
    backend.store(Memory("info", content="private"))
    storage = ThreadStorage(persistent)
    journal = FilesystemOperationRepository(history / "operations" / family)
    thread = Thread("thread", "Title", "Objective", created_at="2026-10-01", updated_at="2026-10-01")
    if family == "thread-create-v1":
        writer = FilesystemLinkedThreadCreation(
            backend, storage, FilesystemEventRepository(history / "events" / family), journal)
        action = lambda: writer.create(thread, "info", operation_id="op", event_id="event")
    elif family == "thread-status-v1":
        storage.create(thread)
        writer = FilesystemThreadOperations(
            storage, FilesystemEventRepository(history / "events" / family), journal)
        action = lambda: writer.change_status("thread", ThreadStatus.VALIDATED,
                                              previous_revision=1, operation_id="op", event_id="event")
    else:
        storage.create(thread)
        writer = FilesystemThreadDeletion(storage, journal)
        action = lambda: writer.delete("thread", previous_revision=1, operation_id="op")
    save = journal.create

    def stop(record):
        save(record)
        raise InterruptedError("after PREPARED")

    with monkeypatch.context() as patch:
        patch.setattr(journal, "create", stop)
        with pytest.raises(InterruptedError):
            action()
    return writer, journal


@pytest.mark.parametrize("family", ["thread-create-v1", "thread-status-v1", "thread-delete-v1"])
def test_failed_is_reported_and_not_modified_by_recovery(tmp_path, monkeypatch, family):
    writer, journal = prepared(tmp_path, family, monkeypatch)
    journal.update(replace(journal.get("op"), status=OperationStatus.FAILED))
    before = hashes(tmp_path)
    assert writer.recover()["op"]["status"] == "BLOCKED"
    state = check_readiness(tmp_path)
    assert not state["ready"]
    assert any(item["reason"] == "FAILED" and not item["resumable"] for item in state["issues"])
    assert not recover_all(tmp_path)["readiness"]["ready"]
    assert hashes(tmp_path) == before


@pytest.mark.parametrize("family", ["thread-create-v1", "thread-status-v1", "thread-delete-v1"])
def test_prepared_work_blocks_then_recovers(tmp_path, monkeypatch, family):
    writer, journal = prepared(tmp_path, family, monkeypatch)
    before = hashes(tmp_path)
    assert not check_readiness(tmp_path)["ready"]
    assert hashes(tmp_path) == before  # No directories or locks added by audit.
    result = recover_all(tmp_path)
    assert result["readiness"]["ready"], result
    assert journal.get("op").status is OperationStatus.COMMITTED
    assert recover_all(tmp_path)["passes"] == 0


def test_recovery_success_claim_cannot_hide_persistent_prepared(tmp_path, monkeypatch):
    prepared(tmp_path, "thread-status-v1", monkeypatch)
    monkeypatch.setattr(FilesystemThreadOperations, "recover", lambda self: {"op": {"status": "COMMITTED"}})
    result = recover_all(tmp_path)
    assert result["passes"] == 1
    assert not result["readiness"]["ready"]
    assert "PREPARED" in result["readiness"]["records"].values()


def test_corrupt_deletion_journal_is_inventory_and_startup_failure(tmp_path):
    path = tmp_path / "memory/history/operations/thread-delete-v1/corrupt.json"
    path.parent.mkdir(parents=True)
    path.write_text("{broken")
    before = hashes(tmp_path)
    assert inventory(tmp_path)["categories"]["thread_delete_operations"] == {"unreadable_or_invalid": 1}
    assert not check_readiness(tmp_path)["ready"]
    assert recover_all(tmp_path)["passes"] == 0
    assert hashes(tmp_path) == before


@pytest.mark.parametrize("relative", [
    "memory/history/future.json", "memory/history/operations/unexpected.bin",
    "memory/history/operations/thread-status-v1/future-v9/op.json",
    "memory/history/operations/future-v9/op.json",
    "memory/history/events/thread-create-v1/orphan.tmp",
])
def test_unknown_history_paths_block_inventory_and_startup(tmp_path, relative):
    path = tmp_path / relative
    path.parent.mkdir(parents=True)
    path.write_text("private")
    before = hashes(tmp_path)
    report = inventory(tmp_path)
    assert any(item["reason"].startswith("unknown_history_") for item in report["needs_review"])
    assert not check_readiness(tmp_path)["ready"]
    assert "private" not in json.dumps(report)
    assert hashes(tmp_path) == before


@pytest.mark.parametrize("linked", ["memory", "memory/history", "memory/history/operations"])
def test_inventory_never_descends_a_linked_ancestor(tmp_path, monkeypatch, linked):
    root, outside = tmp_path / "root", tmp_path / "outside"
    outside.mkdir()
    (outside / "hidden.json").write_text("private")
    link = root / linked
    link.parent.mkdir(parents=True)
    link.symlink_to(outside, target_is_directory=True)
    original = Path.iterdir

    def guarded(path):
        assert outside not in (path.resolve(), *path.resolve().parents)
        return original(path)

    monkeypatch.setattr(Path, "iterdir", guarded)
    result = inventory(root)
    assert any(item["reason"] == "symlink_skipped" for item in result["needs_review"])
    assert not check_readiness(root)["ready"]


def test_registered_lock_and_external_archive_are_not_active_work(tmp_path):
    directory = tmp_path / "memory/history/operations/thread-delete-v1"
    directory.mkdir(parents=True)
    (directory / ".write.lock").touch()
    archive = tmp_path / "archive/history/operations/future-v9"
    archive.mkdir(parents=True)
    (archive / "old.json").write_text("archival bytes")
    before = hashes(tmp_path)
    assert check_readiness(tmp_path)["ready"]
    assert hashes(tmp_path) == before


def test_pending_deletion_is_normal_but_applying_requires_resume(tmp_path, monkeypatch):
    backend = FilesystemBackend(tmp_path / "memory/persistent", tmp_path / "memory/history")
    backend.store(Memory("info", content="text"))
    backend.delete_request("info", "human", "obsolete", 1, "delete-info")
    assert check_readiness(tmp_path)["ready"]
    assert recover_all(tmp_path)["passes"] == 0
    assert backend.get("info") is not None
    original = backend._atomic_write

    def interrupt(path, text):
        original(path, text)
        if path.suffix == ".json" and json.loads(text).get("status") == "APPLYING_DELETE":
            raise InterruptedError("after deletion approval")

    with monkeypatch.context() as patch:
        patch.setattr(backend, "_atomic_write", interrupt)
        with pytest.raises(InterruptedError):
            backend.approve_delete("info", "delete-info")
    assert not check_readiness(tmp_path)["ready"]
    result = recover_all(tmp_path)
    assert result["readiness"]["ready"], result
    assert backend.get("info") is None
    assert result["information-deletions"]["recovered"]


def test_information_write_and_compaction_are_included(tmp_path, monkeypatch):
    backend = FilesystemBackend(tmp_path / "memory/persistent", tmp_path / "memory/history")
    writer = FilesystemInformationWrites(backend)
    original = writer.events.save

    def interrupt(event):
        original(event)
        raise InterruptedError("after Event")

    with monkeypatch.context() as patch:
        patch.setattr(writer.events, "save", interrupt)
        with pytest.raises(InterruptedError):
            writer.create(Memory("info", content="text"), operation_id="op", event_id="event",
                          actor="human", timestamp="2026-10-01T00:00:00Z")
    assert not check_readiness(tmp_path)["ready"]
    assert recover_all(tmp_path)["readiness"]["ready"]
    writer.compact("op")
    assert check_readiness(tmp_path)["ready"]


def test_cli_nonzero_on_failed_and_readiness_is_read_only(tmp_path, monkeypatch):
    _, journal = prepared(tmp_path, "thread-status-v1", monkeypatch)
    journal.update(replace(journal.get("op"), status=OperationStatus.FAILED))
    before = hashes(tmp_path)
    env = dict(os.environ, MEMORY_ENGINE_ROOT=str(tmp_path), PYTHONDONTWRITEBYTECODE="1")
    for command in ("readiness", "recover-all"):
        result = subprocess.run([sys.executable, "-B", "-m", "core.operations.cli", command],
                                env=env, capture_output=True, text=True, timeout=20)
        assert result.returncode == 1, result.stderr
        report = json.loads(result.stdout)
        assert not report.get("readiness", report)["ready"]
    assert hashes(tmp_path) == before


def test_vm_recipe_cannot_pass_a_failed_thread_operation(tmp_path, monkeypatch):
    from tools import vm_acceptance
    source = tmp_path / "source"
    _, journal = prepared(source, "thread-status-v1", monkeypatch)
    journal.update(replace(journal.get("op"), status=OperationStatus.FAILED))
    before = hashes(source)
    monkeypatch.setattr(vm_acceptance, "active_writers", lambda root: [])
    monkeypatch.setattr(vm_acceptance, "discover_writers", lambda: {"running": []})
    monkeypatch.setattr(vm_acceptance.subprocess, "run", lambda *args, **kwargs: type(
        "Result", (), {"returncode": 0, "stdout": "5 passed", "stderr": ""})())
    result = vm_acceptance.run(source, tmp_path / "work", at="2026-10-01T00:00:00Z")
    steps = {item["name"]: item for item in result["steps"]}
    assert steps["startup_readiness"]["status"] == "KO"
    assert not steps["startup_readiness"]["details"]["ready"]
    assert hashes(source) == hashes(tmp_path / "work/restored") == before
