"""Filesystem implementation of the Operation repository."""

from __future__ import annotations

import json
import os
from pathlib import Path

from core.operations.errors import (
    InvalidOperationRecord,
    OperationAlreadyExists,
    OperationConflict,
    OperationNotFound,
)
from core.operations.models import (
    OperationRecord,
    OperationStatus,
    OperationType,
    ThreadStatusChangePlan,
    validate_status_transition,
)
from core.operations.repository import OperationRepository
from core.threads.models import ThreadStatus


class FilesystemOperationRepository(OperationRepository):
    """Persist Operation records as JSON files."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def create(self, operation: OperationRecord) -> None:
        path = self.root / f"{operation.operation_id}.json"

        if path.exists():
            raise OperationAlreadyExists(operation.operation_id)

        self._write(operation, path)

    def get(self, operation_id: str) -> OperationRecord | None:
        path = self.root / f"{operation_id}.json"

        if not path.exists():
            return None

        try:
            with path.open("r", encoding="utf-8") as handle:
                data = json.load(handle)

            if data.get("operation_id") != operation_id:
                raise InvalidOperationRecord(operation_id)

            return OperationRecord(
                operation_id=data["operation_id"],
                operation_type=OperationType(data["operation_type"]),
                target_id=data["target_id"],
                previous_revision=data["previous_revision"],
                revision=data["revision"],
                execution_plan_hash=data["execution_plan_hash"],
                status=OperationStatus(data["status"]),
                plan=(
                    ThreadStatusChangePlan(
                        new_status=ThreadStatus(data["plan"]["new_status"]),
                        event_id=data["plan"]["event_id"],
                    )
                    if data.get("plan") is not None
                    else None
                ),
            )
        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
            raise InvalidOperationRecord(operation_id) from exc

    def update(self, operation: OperationRecord) -> None:
        path = self.root / f"{operation.operation_id}.json"

        if not path.exists():
            raise OperationNotFound(operation.operation_id)

        current = self.get(operation.operation_id)

        immutable_fields_match = (
            current is not None
            and current.operation_type == operation.operation_type
            and current.target_id == operation.target_id
            and current.previous_revision == operation.previous_revision
            and current.revision == operation.revision
            and current.execution_plan_hash == operation.execution_plan_hash
        )

        if not immutable_fields_match:
            raise OperationConflict(operation.operation_id)

        validate_status_transition(current.status, operation.status)

        self._write(operation, path)

    def _write(self, operation: OperationRecord, path: Path) -> None:
        temp_path = path.with_suffix(".json.tmp")

        data = {
            "operation_id": operation.operation_id,
            "operation_type": operation.operation_type.value,
            "target_id": operation.target_id,
            "previous_revision": operation.previous_revision,
            "revision": operation.revision,
            "execution_plan_hash": operation.execution_plan_hash,
            "status": operation.status.value,
            "plan": (
                {
                    "new_status": operation.plan.new_status.value,
                    "event_id": operation.plan.event_id,
                }
                if operation.plan is not None
                else None
            ),
        }

        with temp_path.open("w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2)
            handle.flush()
            os.fsync(handle.fileno())

        os.replace(temp_path, path)

    def list_incomplete(self) -> list[OperationRecord]:
        incomplete_statuses = {
            OperationStatus.PREPARED,
            OperationStatus.APPLYING,
        }

        operations: list[OperationRecord] = []

        for path in sorted(self.root.glob("*.json")):
            operation = self.get(path.stem)

            if operation is not None and operation.status in incomplete_statuses:
                operations.append(operation)

        return operations
