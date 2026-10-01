"""Filesystem implementation of the Operation repository."""

from __future__ import annotations

import json
import re
from dataclasses import asdict
from pathlib import Path

from core.persistence import serialized_write, atomic_write_text, has_symlink_component
from core.storage_format import parse_finite_json_float

from core.operations.errors import (
    InvalidOperationRecord,
    OperationAlreadyExists,
    OperationConflict,
    OperationNotFound,
)
from core.operations.models import (
    InformationCreatePlan,
    InformationUpdatePlan,
    OperationRecord,
    OperationStatus,
    OperationType,
    ThreadCreatePlan,
    ThreadDeletePlan,
    ThreadUpdatePlan,
    ThreadStatusChangePlan,
    validate_status_transition,
)
from core.operations.repository import OperationRepository
from core.threads.models import ThreadStatus


class FilesystemOperationRepository(OperationRepository):
    """Persist Operation records as JSON files."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        if has_symlink_component(self.root):
            raise InvalidOperationRecord("Operation directory is a symlink")
        self.root.mkdir(parents=True, exist_ok=True)
        if has_symlink_component(self.root):
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
            def unique_object(pairs):
                result = {}
                for key, value in pairs:
                    if key in result:
                        raise ValueError("duplicate Operation JSON key")
                    result[key] = value
                return result

            def invalid_constant(value):
                raise ValueError("invalid Operation JSON constant")

            with path.open("r", encoding="utf-8") as handle:
                data = json.load(handle, object_pairs_hook=unique_object,
                                 parse_constant=invalid_constant,
                                 parse_float=parse_finite_json_float)

            if not isinstance(data, dict) or data.get("operation_id") != operation_id:
                raise InvalidOperationRecord(operation_id)
            allowed = {
                "operation_id", "operation_type", "target_id", "previous_revision",
                "revision", "execution_plan_hash", "status", "plan",
            }
            if data.keys() - allowed:
                raise InvalidOperationRecord("unknown Operation fields")
            plan = data.get("plan")
            if isinstance(plan, dict):
                if data.get("operation_type") in {
                    OperationType.INFORMATION_CREATE.value, OperationType.INFORMATION_UPDATE.value,
                }:
                    plan_allowed = {"event_id", "after_state", "actor", "timestamp", "command_fingerprint"}
                    if data["operation_type"] == OperationType.INFORMATION_UPDATE.value:
                        plan_allowed.add("before_state")
                elif data.get("operation_type") == OperationType.THREAD_UPDATE.value:
                    plan_allowed = {"command", "event_id", "actor", "timestamp", "before_state", "after_state"}
                elif data.get("operation_type") == OperationType.THREAD_CREATE.value:
                    plan_allowed = {"information_id", "event_id", "after_state"}
                elif data.get("operation_type") == OperationType.THREAD_DELETE.value:
                    plan_allowed = {"before_state"}
                else:
                    plan_allowed = {"new_status", "event_id", "before_state", "after_state"}
                if plan.keys() - plan_allowed:
                    raise InvalidOperationRecord("unknown Operation plan fields")

            record = OperationRecord(
                operation_id=data["operation_id"],
                operation_type=OperationType(data["operation_type"]),
                target_id=data["target_id"],
                previous_revision=data["previous_revision"],
                revision=data["revision"],
                execution_plan_hash=data["execution_plan_hash"],
                status=OperationStatus(data["status"]),
                plan=(
                    InformationCreatePlan(**data["plan"])
                    if data["operation_type"] == OperationType.INFORMATION_CREATE.value
                    else InformationUpdatePlan(**data["plan"])
                    if data["operation_type"] == OperationType.INFORMATION_UPDATE.value
                    else ThreadUpdatePlan(**data["plan"])
                    if data["operation_type"] == OperationType.THREAD_UPDATE.value
                    else ThreadCreatePlan(
                        information_id=data["plan"]["information_id"],
                        event_id=data["plan"]["event_id"],
                        after_state=data["plan"]["after_state"],
                    )
                    if data.get("plan") is not None
                    and data["operation_type"] == OperationType.THREAD_CREATE.value
                    else ThreadDeletePlan(before_state=data["plan"]["before_state"])
                    if data.get("plan") is not None
                    and data["operation_type"] == OperationType.THREAD_DELETE.value
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
            self._validate_record_fields(record)
            return record
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

    @staticmethod
    def _validate_record_fields(operation: OperationRecord) -> None:
        def valid_id(value):
            return isinstance(value, str) and bool(re.fullmatch(r"[A-Za-z0-9._-]+", value))

        if (not valid_id(operation.operation_id) or not valid_id(operation.target_id)
                or not isinstance(operation.execution_plan_hash, str)
                or not isinstance(operation.status, OperationStatus)
                or not isinstance(operation.operation_type, OperationType)):
            raise InvalidOperationRecord("invalid Operation identity or status")
        plan = operation.plan
        if isinstance(plan, InformationCreatePlan):
            if (not valid_id(plan.event_id)
                    or any(not isinstance(value, str) for value in
                           (plan.after_state, plan.actor, plan.timestamp, plan.command_fingerprint))
                    or (isinstance(plan, InformationUpdatePlan) and not isinstance(plan.before_state, str))):
                raise InvalidOperationRecord("invalid Information write plan")
        elif isinstance(plan, ThreadUpdatePlan):
            if (not valid_id(plan.event_id) or any(not isinstance(value, str) for value in
                    (plan.command, plan.actor, plan.timestamp, plan.before_state, plan.after_state))):
                raise InvalidOperationRecord("invalid Thread update plan")
        elif isinstance(plan, ThreadCreatePlan):
            if (not valid_id(plan.information_id) or not valid_id(plan.event_id)
                    or not isinstance(plan.after_state, str)):
                raise InvalidOperationRecord("invalid Thread creation plan")
        elif isinstance(plan, ThreadDeletePlan):
            if not isinstance(plan.before_state, str):
                raise InvalidOperationRecord("invalid Thread deletion plan")
        elif isinstance(plan, ThreadStatusChangePlan):
            if (not isinstance(plan.new_status, ThreadStatus) or not valid_id(plan.event_id)
                    or any(value is not None and not isinstance(value, str)
                           for value in (plan.before_state, plan.after_state))):
                raise InvalidOperationRecord("invalid Thread status plan")
        else:
            raise InvalidOperationRecord("invalid Operation plan")

    def _write(self, operation: OperationRecord, path: Path) -> None:
        self._validate_record_fields(operation)
        data = {
            "operation_id": operation.operation_id,
            "operation_type": operation.operation_type.value,
            "target_id": operation.target_id,
            "previous_revision": operation.previous_revision,
            "revision": operation.revision,
            "execution_plan_hash": operation.execution_plan_hash,
            "status": operation.status.value,
            "plan": (
                asdict(operation.plan)
                if isinstance(operation.plan, (InformationCreatePlan, ThreadUpdatePlan))
                else {
                    "information_id": operation.plan.information_id,
                    "event_id": operation.plan.event_id,
                    "after_state": operation.plan.after_state,
                }
                if isinstance(operation.plan, ThreadCreatePlan)
                else {"before_state": operation.plan.before_state}
                if isinstance(operation.plan, ThreadDeletePlan)
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

        try:
            content = json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False)
        except (TypeError, ValueError) as exc:
            raise InvalidOperationRecord("Operation cannot be serialized as JSON") from exc
        atomic_write_text(path, content)

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
