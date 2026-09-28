"""Run with python -m core.operations.cli; uses isolated v1 journals."""
import argparse
import hashlib
import json

from core.config import PERSISTENT_ROOT, HISTORY_ROOT, OPERATIONS_ROOT, EVENTS_ROOT
from core.backend.filesystem import FilesystemBackend
from core.events.filesystem import FilesystemEventRepository
from core.operations.filesystem import FilesystemOperationRepository
from core.operations.thread_status import FilesystemThreadOperations
from core.operations.thread_create import FilesystemLinkedThreadCreation
from core.threads.models import ThreadStatus
from core.threads.storage import ThreadStorage
from core.threads.service import ThreadService
from core.threads.serialization import thread_to_dict


def main():
    parser = argparse.ArgumentParser(description="Recoverable Thread status operations")
    commands = parser.add_subparsers(dest="command", required=True)
    change = commands.add_parser("change-status")
    change.add_argument("thread_id")
    change.add_argument("status", choices=[status.value for status in ThreadStatus])
    change.add_argument("--previous-revision", type=int, required=True)
    change.add_argument("--operation-id", required=True)
    change.add_argument("--event-id")
    commands.add_parser("recover")
    commands.add_parser("recover-creations")
    args = parser.parse_args()
    storage = ThreadStorage(PERSISTENT_ROOT)
    if args.command == "recover-creations":
        creation = FilesystemLinkedThreadCreation(
            FilesystemBackend(PERSISTENT_ROOT, HISTORY_ROOT), storage,
            FilesystemEventRepository(EVENTS_ROOT / "thread-create-v1"),
            FilesystemOperationRepository(OPERATIONS_ROOT / "thread-create-v1"),
        )
        result = creation.recover()
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return int(any(record["status"] == "BLOCKED" for record in result.values()))
    service = ThreadService(storage, FilesystemThreadOperations(
        storage, FilesystemEventRepository(EVENTS_ROOT / "thread-status-v1"),
        FilesystemOperationRepository(OPERATIONS_ROOT / "thread-status-v1"),
    ))
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
