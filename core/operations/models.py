"""Domain models for Eidolon Memory Operations."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class OperationStatus(str, Enum):
    """Lifecycle states of a persistent operation."""

    PREPARED = "PREPARED"
    APPLYING = "APPLYING"
    COMMITTED = "COMMITTED"
    FAILED = "FAILED"


class OperationType(str, Enum):
    """Supported persistent operation types."""

    THREAD_STATUS_CHANGE = "THREAD_STATUS_CHANGE"


@dataclass
class OperationRecord:
    """Technical record for a recoverable persistent operation."""

    operation_id: str
    operation_type: OperationType
    target_id: str
    previous_revision: int
    revision: int
    execution_plan_hash: str
    status: OperationStatus = OperationStatus.PREPARED

    def __post_init__(self) -> None:
        if self.revision != self.previous_revision + 1:
            raise ValueError(
                "revision must equal previous_revision + 1"
            )


def validate_status_transition(
    current: OperationStatus,
    new: OperationStatus,
) -> None:
    """Validate an Operation lifecycle transition."""

    allowed = {
        OperationStatus.PREPARED: {
            OperationStatus.APPLYING,
            OperationStatus.FAILED,
        },
        OperationStatus.APPLYING: {
            OperationStatus.COMMITTED,
            OperationStatus.FAILED,
        },
        OperationStatus.COMMITTED: set(),
        OperationStatus.FAILED: set(),
    }

    if new not in allowed[current]:
        raise ValueError(
            f"invalid Operation status transition: {current.value} -> {new.value}"
        )
