"""Run with python -m core.operations.cli; uses isolated v1 journals."""
import argparse
import hashlib
import json

from core.config import ENGINE_ROOT, PERSISTENT_ROOT, HISTORY_ROOT, OPERATIONS_ROOT, EVENTS_ROOT
from core.preflight import check_environment
from core.backend.filesystem import FilesystemBackend
from core.events.filesystem import FilesystemEventRepository
from core.operations.filesystem import FilesystemOperationRepository
from core.operations.thread_status import FilesystemThreadOperations
from core.operations.thread_create import FilesystemLinkedThreadCreation
from core.operations.thread_delete import FilesystemThreadDeletion
from core.threads.models import Thread, ThreadStatus
from core.threads.storage import ThreadStorage
from core.threads.service import ThreadService
from core.threads.serialization import thread_to_dict
from core.operations.readiness import check_readiness, recover_all


def main():
    parser = argparse.ArgumentParser(description="Recoverable Thread operations")
    commands = parser.add_subparsers(dest="command", required=True)
    linked = commands.add_parser("create-linked")
    linked.add_argument("thread_id")
    linked.add_argument("information_id")
    linked.add_argument("--title", required=True)
    linked.add_argument("--objective", required=True)
    linked.add_argument("--created-at", required=True)
    linked.add_argument("--operation-id", required=True)
    linked.add_argument("--event-id")
    change = commands.add_parser("change-status")
    change.add_argument("thread_id")
    change.add_argument("status", choices=[status.value for status in ThreadStatus])
    change.add_argument("--previous-revision", type=int, required=True)
    change.add_argument("--operation-id", required=True)
    change.add_argument("--event-id")
    commands.add_parser("recover")
    commands.add_parser("recover-creations")
    commands.add_parser("recover-deletions")
    commands.add_parser("recover-all")
    commands.add_parser("readiness", help="Read-only startup gate on a stopped tree")
    deletion_command = commands.add_parser("delete-thread")
    deletion_command.add_argument("thread_id")
    deletion_command.add_argument("--previous-revision", type=int, required=True)
    deletion_command.add_argument("--operation-id", required=True)
    args = parser.parse_args()
    if args.command == "readiness":
        result = check_readiness(ENGINE_ROOT)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return int(not result["ready"])
    check_environment(ENGINE_ROOT)
    if args.command == "recover-all":
        result = recover_all(ENGINE_ROOT)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return int(not result["readiness"]["ready"])
    storage = ThreadStorage(PERSISTENT_ROOT)
    deletion = None
    if args.command in {"delete-thread", "recover-deletions"}:
        deletion = FilesystemThreadDeletion.for_history(storage, HISTORY_ROOT)
        if args.command == "delete-thread":
            deletion.delete(args.thread_id, previous_revision=args.previous_revision,
                            operation_id=args.operation_id)
            print(json.dumps({"thread_id": args.thread_id, "status": "DELETED"}))
            return 0
        if args.command == "recover-deletions":
            result = deletion.recover()
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return int(any(record["status"] == "BLOCKED" for record in result.values()))
    if args.command in {"recover-creations", "create-linked"}:
        creation = FilesystemLinkedThreadCreation(
            FilesystemBackend(PERSISTENT_ROOT, HISTORY_ROOT), storage,
            FilesystemEventRepository(EVENTS_ROOT / "thread-create-v1"),
            FilesystemOperationRepository(OPERATIONS_ROOT / "thread-create-v1"),
            deletion_operations=FilesystemOperationRepository(
                OPERATIONS_ROOT / "thread-delete-v1"),
        )
        if args.command == "recover-creations":
            result = creation.recover()
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return int(any(record["status"] == "BLOCKED" for record in result.values()))
        if args.command == "create-linked":
            event_id = args.event_id or "created-" + hashlib.sha256(args.operation_id.encode()).hexdigest()
            result = ThreadService(storage, creation=creation).create_linked(
                Thread(args.thread_id, args.title, args.objective,
                       created_at=args.created_at, updated_at=args.created_at),
                args.information_id, operation_id=args.operation_id, event_id=event_id,
            )
            print(json.dumps(thread_to_dict(result), ensure_ascii=False, indent=2))
            return 0
    service = ThreadService(storage, FilesystemThreadOperations(
        storage, FilesystemEventRepository(EVENTS_ROOT / "thread-status-v1"),
        FilesystemOperationRepository(OPERATIONS_ROOT / "thread-status-v1"),
        FilesystemOperationRepository(OPERATIONS_ROOT / "thread-create-v1"),
        FilesystemOperationRepository(OPERATIONS_ROOT / "thread-delete-v1"),
    ), deletion=deletion)
    if args.command == "recover":
        result = service.recover()
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return int(any(record["status"] == "BLOCKED" for record in result.values()))
    event_id = args.event_id or "event-" + hashlib.sha256(args.operation_id.encode()).hexdigest()
    result = service.change_status(
        args.thread_id, ThreadStatus(args.status), previous_revision=args.previous_revision,
        operation_id=args.operation_id, event_id=event_id,
    )
    print(json.dumps(thread_to_dict(result), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
