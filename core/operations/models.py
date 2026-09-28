"""Domain models for Eidolon Memory Operations."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from core.threads.models import ThreadStatus


class OperationStatus(str, Enum):
    """Lifecycle states of a persistent operation."""

    PREPARED = "PREPARED"
    APPLYING = "APPLYING"
    COMMITTED = "COMMITTED"
    FAILED = "FAILED"


class OperationType(str, Enum):
    """Supported persistent operation types."""

    THREAD_STATUS_CHANGE = "THREAD_STATUS_CHANGE"
    THREAD_CREATE = "THREAD_CREATE"


@dataclass(frozen=True)
class ThreadStatusChangePlan:
    """Recoverable plan for a Thread status change."""

    new_status: ThreadStatus
    event_id: str
    before_state: str | None = None
    after_state: str | None = None


@dataclass(frozen=True)
class ThreadCreatePlan:
    """Recoverable linked Thread creation snapshot."""

    information_id: str
    event_id: str
    after_state: str


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
    plan: ThreadStatusChangePlan | ThreadCreatePlan | None = None

    def __post_init__(self) -> None:
        if self.revision != self.previous_revision + 1:
            raise ValueError(
                "revision must equal previous_revision + 1"
            )

        if (
            self.operation_type is OperationType.THREAD_STATUS_CHANGE
            and not isinstance(self.plan, ThreadStatusChangePlan)
        ):
            raise ValueError(
                "THREAD_STATUS_CHANGE requires a recovery plan"
            )
        if self.operation_type is OperationType.THREAD_CREATE and (
            self.previous_revision != 0 or not isinstance(self.plan, ThreadCreatePlan)
        ):
            raise ValueError("THREAD_CREATE requires revision 1 and a creation plan")


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
