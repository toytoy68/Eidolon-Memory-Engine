"""Filesystem implementation of the Operation repository."""

from __future__ import annotations

import json
import re
from pathlib import Path

from core.persistence import serialized_write, atomic_write_text

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
    ThreadCreatePlan,
    ThreadStatusChangePlan,
    validate_status_transition,
)
from core.operations.repository import OperationRepository
from core.threads.models import ThreadStatus


class FilesystemOperationRepository(OperationRepository):
    """Persist Operation records as JSON files."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        if self.root.is_symlink():
            raise InvalidOperationRecord("Operation directory is a symlink")
        self.root.mkdir(parents=True, exist_ok=True)
        if self.root.is_symlink():
            raise InvalidOperationRecord("Operation directory is a symlink")

    def _path(self, operation_id: str) -> Path:
        if (not isinstance(operation_id, str)
                or not re.fullmatch(r"[A-Za-z0-9._-]+", operation_id)):
            raise InvalidOperationRecord("invalid operation_id")
        path = self.root / f"{operation_id}.json"
        if path.resolve().parent != self.root.resolve():
            raise InvalidOperationRecord("operation path escapes repository")
        return path

    @serialized_write("root")
    def create(self, operation: OperationRecord) -> None:
        path = self._path(operation.operation_id)

        if path.exists() or path.is_symlink():
            raise OperationAlreadyExists(operation.operation_id)

        self._write(operation, path)

    def get(self, operation_id: str) -> OperationRecord | None:
        path = self._path(operation_id)

        if path.is_symlink():
            raise InvalidOperationRecord("Operation path is a symlink")
        if not path.exists():
            return None

        try:
            with path.open("r", encoding="utf-8") as handle:
                data = json.load(handle)

            if not isinstance(data, dict) or data.get("operation_id") != operation_id:
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
                    ThreadCreatePlan(
                        information_id=data["plan"]["information_id"],
                        event_id=data["plan"]["event_id"],
                        after_state=data["plan"]["after_state"],
                    )
                    if data.get("plan") is not None
                    and data["operation_type"] == OperationType.THREAD_CREATE.value
                    else ThreadStatusChangePlan(
                        new_status=ThreadStatus(data["plan"]["new_status"]),
                        event_id=data["plan"]["event_id"],
                        before_state=data["plan"].get("before_state"),
                        after_state=data["plan"].get("after_state"),
                    )
                    if data.get("plan") is not None
                    else None
                ),
            )
        except (OSError, UnicodeError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
            raise InvalidOperationRecord(operation_id) from exc

    @serialized_write("root")
    def update(self, operation: OperationRecord) -> None:
        path = self._path(operation.operation_id)

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
            and current.plan == operation.plan
        )

        if not immutable_fields_match:
            raise OperationConflict(operation.operation_id)

        validate_status_transition(current.status, operation.status)

        self._write(operation, path)

    def _write(self, operation: OperationRecord, path: Path) -> None:
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
                    "information_id": operation.plan.information_id,
                    "event_id": operation.plan.event_id,
                    "after_state": operation.plan.after_state,
                }
                if isinstance(operation.plan, ThreadCreatePlan)
                else {
                    "new_status": operation.plan.new_status.value,
                    "event_id": operation.plan.event_id,
                    "before_state": operation.plan.before_state,
                    "after_state": operation.plan.after_state,
                }
                if operation.plan is not None
                else None
            ),
        }

        atomic_write_text(path, json.dumps(data, ensure_ascii=False, indent=2))

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
