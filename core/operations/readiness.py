"""Read-only startup gate and explicit recovery on a stopped engine tree.

This is a point-in-time check, not a lease against concurrent/legacy writers.
Never turn FAILED into a successful operation or approve a pending deletion.
"""
from pathlib import Path

from core.information.deletion_audit import audit_deletions
from core.migration.inventory import inventory, symlink_ancestor, invalid_directory_ancestor
from core.operations.errors import OperationRepositoryError
from core.operations.filesystem import FilesystemOperationRepository
from core.operations.models import OperationStatus, OperationType
from core.operations.thread_status import plan_hash


THREAD_FAMILIES = {
    "thread-create-v1": OperationType.THREAD_CREATE,
    "thread-status-v1": OperationType.THREAD_STATUS_CHANGE,
    "thread-delete-v1": OperationType.THREAD_DELETE,
    "thread-update-v1": OperationType.THREAD_UPDATE,
}


def check_readiness(engine_root: Path) -> dict:
    """Report every unresolved journal, including states recover() may omit."""
    root = Path(engine_root)
    formats = inventory(root)
    issues = [dict(item, resumable=False) for item in formats["needs_review"]
              if item["path"] != "memory/history/information-write-v1"]
    records = {}
    for family, expected_type in THREAD_FAMILIES.items():
        directory = root / "memory/history/operations" / family
        if (symlink_ancestor(root, directory)
                or invalid_directory_ancestor(root, directory)):
            continue  # Already blocked by inventory, without traversing the path.
        repository = FilesystemOperationRepository.__new__(FilesystemOperationRepository)
        repository.root = directory  # Reader only: __init__ would mkdir.
        for path in sorted(directory.glob("*.json")):
            relative = path.relative_to(root).as_posix()
            try:
                operation = repository.get(path.stem)
                if operation is None:
                    raise ValueError("journal disappeared during stopped-copy check")
                if (operation.operation_type is not expected_type
                        or plan_hash(operation) != operation.execution_plan_hash):
                    raise ValueError("journal family or plan hash mismatch")
                status = operation.status.value
                records[relative] = status
                if operation.status is not OperationStatus.COMMITTED:
                    issues.append({"path": relative, "reason": status,
                                   "resumable": operation.status in {
                                       OperationStatus.PREPARED, OperationStatus.APPLYING}})
            except (OSError, ValueError, TypeError, OperationRepositoryError) as exc:
                records[relative] = "BLOCKED"
                issues.append({"path": relative, "reason": type(exc).__name__, "resumable": False})

    # The old unversioned operation directory is archival input, not a core
    # recovery family. Do not execute or silently accept its records at startup.
    for kind, count in formats["categories"]["operations"].items():
        if count:
            issues.append({"path": "memory/history/operations", "reason": "unmigrated_operations",
                           "resumable": False})
            break

    writes = formats["information_writes"]
    for opid, record in writes["records"].items():
        records[f"information-write-v1/{opid}"] = record["status"]
    for item in writes["issues"]:
        status = writes["records"].get(item["operation_id"], {}).get("status")
        issues.append({"path": "memory/history/information-write-v1",
                       **item, "resumable": status in {"PREPARED", "APPLYING", "COMPACTING"}})
    from core.routing.execution_journal import audit_executions
    executions = audit_executions(root)
    records.update(executions['records'])
    issues.extend(executions['issues'])
    from core.lifecycle.journal import audit_triggers
    triggers = audit_triggers(root)
    records.update(triggers['records'])
    issues.extend(triggers['issues'])
    deletions = audit_deletions(root)
    for item in deletions["issues"]:
        issues.append({"path": item["request"], "reason": item["reason"],
                       "resumable": item["reason"] == "deletion_requires_resume"})
    return {"ready": not issues, "issues": issues, "records": records,
            "information_deletions": deletions,
            "scope": "stopped_tree_point_in_time_no_concurrent_writers"}


def recover_all(engine_root: Path) -> dict:
    """Recover known work, retry dependencies only while durable progress occurs.

    Unknown/corrupt/FAILED records require review before any automatic recovery.
    Final readiness always comes from a fresh disk audit, not coordinator claims.
    """
    from core.backend.filesystem import FilesystemBackend
    from core.events.filesystem import FilesystemEventRepository
    from core.information.deletion_recovery import recover_deletions
    from core.information.writes import FilesystemInformationWrites
    from core.operations.thread_create import FilesystemLinkedThreadCreation
    from core.operations.thread_delete import FilesystemThreadDeletion
    from core.operations.thread_status import FilesystemThreadOperations
    from core.operations.thread_update import FilesystemThreadUpdates
    from core.threads.storage import ThreadStorage

    root = Path(engine_root)
    report = {"creations": {}, "status_changes": {}, "deletions": {},
              "information-writes": {}, "information-deletions": {}, "thread-updates": {}, "routing-executions": {}, "lifecycle-triggers": {}, "passes": 0}
    state = check_readiness(root)
    report["information-writes"] = {
        path.split("/", 1)[1]: {"status": "COMMITTED"}
        for path, status in state["records"].items()
        if path.startswith("information-write-v1/") and status in {"COMMITTED", "COMPACTED"}
    }
    if state["ready"] or any(not item["resumable"] for item in state["issues"]):
        return dict(report, readiness=state)
    history = root / "memory/history"
    backend = FilesystemBackend(root / "memory/persistent", history)
    storage = ThreadStorage(backend.persistent_root)
    journals = {name: FilesystemOperationRepository(history / "operations" / name)
                for name in THREAD_FAMILIES}
    creation = FilesystemLinkedThreadCreation(
        backend, storage, FilesystemEventRepository(history / "events/thread-create-v1"),
        journals["thread-create-v1"], deletion_operations=journals["thread-delete-v1"])
    changes = FilesystemThreadOperations(
        storage, FilesystemEventRepository(history / "events/thread-status-v1"),
        journals["thread-status-v1"], journals["thread-create-v1"], journals["thread-delete-v1"])
    deletion = FilesystemThreadDeletion(
        storage, journals["thread-delete-v1"], status_operations=journals["thread-status-v1"],
        creation_operations=journals["thread-create-v1"])
    writes = FilesystemInformationWrites(backend)
    updates = FilesystemThreadUpdates(backend)
    from core.routing.execution import RoutingExecutor
    executor = RoutingExecutor(backend)
    from core.lifecycle.service import LifecycleTriggers
    lifecycle = LifecycleTriggers(backend)

    # On a stopped tree each successful pass removes at least one issue. This
    # bound also prevents looping if a noncooperating writer changes the tree.
    for _ in range(len(state["issues"]) + 1):
        previous = state
        for name, action in (("lifecycle-triggers", lifecycle.recover), ("routing-executions", executor.recover), ("creations", creation.recover), ("status_changes", changes.recover),
                             ("thread-updates", updates.recover), ("deletions", deletion.recover), ("information-writes", writes.recover)):
            report[name].update(action())
        report["information-deletions"] = recover_deletions(root)
        report["passes"] += 1
        state = check_readiness(root)
        if (state["ready"] or any(not item["resumable"] for item in state["issues"])
                or state == previous):
            break
    report["readiness"] = state
    return report
