from dataclasses import replace
import json
import multiprocessing
import os
from pathlib import Path

import pytest

from core.events.filesystem import FilesystemEventRepository
from core.events.models import Event, EventType
from core.operations.errors import OperationConflict
from core.operations.filesystem import FilesystemOperationRepository
from core.operations.models import (OperationRecord, OperationStatus, OperationType,
                                    ThreadCreatePlan)
from core.operations.thread_status import FilesystemThreadOperations, plan_hash
from core.threads.models import Thread, ThreadStatus
from core.threads.storage import ThreadStorage
from core.threads.service import ThreadService


def coordinator(root):
    root = Path(root)
    return FilesystemThreadOperations(ThreadStorage(root / "persistent"),
                                     FilesystemEventRepository(root / "events"),
                                     FilesystemOperationRepository(root / "operations"))


def seed(root):
    engine = coordinator(root)
    thread = Thread("t", "Title", "Objective", created_at="2026-01-01T00:00:00+00:00",
                    updated_at="2026-01-01T00:00:00+00:00")
    engine.storage.create(thread)
    return engine, thread


def change(engine, **kwargs):
    arguments = dict(previous_revision=1, operation_id="op", event_id="e")
    arguments.update(kwargs)
    return engine.change_status("t", ThreadStatus.VALIDATED, **arguments)


def crash_worker(root, phase):
    engine = coordinator(root)
    if phase == "prepared":
        target, method = engine.operations, "create"
    elif phase in {"applying", "committed"}:
        target, method = engine.operations, "update"
    elif phase == "thread":
        target, method = engine.storage, "update"
    else:
        target, method = engine.events, "save"
    original = getattr(target, method)
    def interrupted(*args, **kwargs):
        result = original(*args, **kwargs)
        if method == "update" and target is engine.operations:
            expected = OperationStatus.APPLYING if phase == "applying" else OperationStatus.COMMITTED
            if args[0].status != expected:
                return result
        os._exit(73)
    setattr(target, method, interrupted)
    change(engine)


@pytest.mark.parametrize("phase", ["prepared", "applying", "thread", "event", "committed"])
def test_hard_process_exit_at_each_boundary_is_recoverable(tmp_path, phase):
    engine, original = seed(tmp_path)
    process = multiprocessing.get_context("spawn").Process(
        target=crash_worker, args=(str(tmp_path), phase))
    process.start()
    process.join(timeout=20)
    if process.is_alive():
        process.terminate()
        process.join()
        pytest.fail("operation deadlocked")
    assert process.exitcode == 73
    restarted = coordinator(tmp_path)
    prepared = restarted.operations.get("op")
    expected = restarted.storage._deserialize(prepared.plan.after_state)
    assert restarted.recover().get("op", {"status": "COMMITTED"})["status"] == "COMMITTED"
    assert restarted.storage.get("t") == expected
    assert expected.revision == original.revision + 1
    assert restarted.operations.get("op").status == OperationStatus.COMMITTED
    events = restarted.events.list_for_target("t")
    assert len(events) == 1
    assert events[0].provenance.timestamp == expected.updated_at
    assert change(restarted) == expected
    assert restarted.recover() == {}


def test_service_integrates_mutation_and_idempotent_replay(tmp_path):
    engine, _ = seed(tmp_path)
    service = ThreadService(engine.storage, engine)
    result = service.change_status("t", ThreadStatus.VALIDATED,
        previous_revision=1, operation_id="op", event_id="e")
    assert result.status == ThreadStatus.VALIDATED
    later = engine.change_status("t", ThreadStatus.IMPLEMENTATION,
        previous_revision=2, operation_id="op2", event_id="e2")
    assert change(engine) == result
    assert engine.storage.get("t") == later
    assert service.recover() == {}


def test_status_command_rejects_creation_record_with_same_id(tmp_path):
    engine, before = seed(tmp_path)
    engine.operations.create(OperationRecord(
        "op", OperationType.THREAD_CREATE, "t", 0, 1, "hash",
        plan=ThreadCreatePlan("info-1", "e", "snapshot")))
    with pytest.raises(OperationConflict, match="different command"):
        engine.change_status("t", ThreadStatus.VALIDATED,
                             previous_revision=0, operation_id="op", event_id="e")
    assert engine.storage.get("t") == before
    assert engine.events.get("e") is None


def test_reused_operation_id_cannot_change_command(tmp_path):
    engine, _ = seed(tmp_path)
    change(engine)
    with pytest.raises(OperationConflict):
        change(engine, event_id="different")


def prepare_only(engine, monkeypatch):
    original = engine.operations.create
    def stop(operation):
        original(operation)
        raise InterruptedError("after prepare")
    monkeypatch.setattr(engine.operations, "create", stop)
    with pytest.raises(InterruptedError):
        change(engine)
    return engine.operations.get("op")


def test_recovery_refuses_divergent_thread(tmp_path, monkeypatch):
    engine, before = seed(tmp_path)
    prepare_only(engine, monkeypatch)
    engine.storage.update(replace(before, revision=2, title="External edit"), 1)
    result = engine.recover()
    assert result["op"]["status"] == "BLOCKED"
    assert engine.storage.get("t").title == "External edit"
    assert engine.events.get("e") is None


def test_pending_operation_blocks_new_change(tmp_path, monkeypatch):
    engine, _ = seed(tmp_path)
    prepare_only(engine, monkeypatch)
    with pytest.raises(OperationConflict, match="pending"):
        change(engine, operation_id="new", event_id="new-event")


def test_event_collision_does_not_modify_thread(tmp_path):
    engine, before = seed(tmp_path)
    engine.events.save(Event("e", 1, EventType.CREATED, information_id="unrelated"))
    with pytest.raises(OperationConflict, match="different event"):
        change(engine)
    assert engine.storage.get("t") == before


def test_hash_tampering_is_reported_without_writes(tmp_path, monkeypatch):
    engine, before = seed(tmp_path)
    prepare_only(engine, monkeypatch)
    path = engine.operations.root / "op.json"
    payload = json.loads(path.read_text())
    payload["plan"]["event_id"] = "tampered"
    path.write_text(json.dumps(payload))
    assert engine.recover()["op"]["status"] == "BLOCKED"
    assert engine.storage.get("t") == before


def test_corrupt_record_does_not_prevent_other_recovery(tmp_path, monkeypatch):
    engine, _ = seed(tmp_path)
    prepare_only(engine, monkeypatch)
    (engine.operations.root / "aaa.json").write_text("[]")
    results = engine.recover()
    assert results["aaa"]["status"] == "BLOCKED"
    assert results["op"]["status"] == "COMMITTED"


def test_legacy_plan_is_not_guessed(tmp_path, monkeypatch):
    engine, before = seed(tmp_path)
    operation = prepare_only(engine, monkeypatch)
    path = engine.operations.root / "op.json"
    payload = json.loads(path.read_text())
    payload["plan"].pop("before_state")
    payload["plan"].pop("after_state")
    path.write_text(json.dumps(payload))
    assert engine.recover()["op"] == {"status": "BLOCKED", "error": "OperationConflict"}
    assert engine.storage.get("t") == before


def test_plan_snapshots_round_trip(tmp_path):
    engine, before = seed(tmp_path)
    after = change(engine)
    operation = coordinator(tmp_path).operations.get("op")
    assert plan_hash(operation) == operation.execution_plan_hash
    assert engine.storage._deserialize(operation.plan.before_state) == before
    assert engine.storage._deserialize(operation.plan.after_state) == after


def competing_command(root, barrier):
    engine = coordinator(root)
    barrier.wait(timeout=15)
    return change(engine)


def test_concurrent_retries_commit_exactly_once(tmp_path):
    from concurrent.futures import ProcessPoolExecutor
    seed(tmp_path)
    context = multiprocessing.get_context("spawn")
    with context.Manager() as manager:
        barrier = manager.Barrier(2)
        with ProcessPoolExecutor(2, mp_context=context) as pool:
            futures = [pool.submit(competing_command, str(tmp_path), barrier) for _ in range(2)]
            results = [future.result(timeout=30) for future in futures]
    assert results[0] == results[1]
    engine = coordinator(tmp_path)
    assert engine.storage.get("t").revision == 2
    assert len(engine.events.list_for_target("t")) == 1


def test_cli_uses_separate_journals_and_replays(tmp_path):
    import subprocess
    import sys
    storage = ThreadStorage(tmp_path / "memory" / "persistent")
    storage.create(Thread("t", "Title", "Objective", created_at="2026-01-01",
                          updated_at="2026-01-01"))
    environment = dict(os.environ, MEMORY_ENGINE_ROOT=str(tmp_path), PYTHONDONTWRITEBYTECODE="1")
    command = [sys.executable, "-m", "core.operations.cli", "change-status", "t", "VALIDATED",
               "--previous-revision", "1", "--operation-id", "cli-op"]
    first = subprocess.run(command, env=environment, capture_output=True, text=True, check=True)
    second = subprocess.run(command, env=environment, capture_output=True, text=True, check=True)
    assert json.loads(first.stdout) == json.loads(second.stdout)
    result = subprocess.run([sys.executable, "-m", "core.operations.cli", "recover"],
                            env=environment, capture_output=True, text=True, check=True)
    assert json.loads(result.stdout) == {}
    assert (tmp_path / "memory/history/operations/thread-status-v1/cli-op.json").is_file()
