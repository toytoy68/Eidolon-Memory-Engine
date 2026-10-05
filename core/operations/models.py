# ==========================================================
# Projet      : Eidolon Memory Engine
# Organisation: Eidolon Core Technologies (ECT)
# Fichier     : core/operations/models.py
# Description : Domain models for Eidolon Memory Operations.
# Standard    : Eidolon Presentation Standard v1
# ==========================================================

"""Domain models for Eidolon Memory Operations."""

from __future__ import annotations

from dataclasses import dataclass, field
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
    THREAD_DELETE = "THREAD_DELETE"
    THREAD_UPDATE = "THREAD_UPDATE"
    INFORMATION_CREATE = "INFORMATION_CREATE"
    INFORMATION_UPDATE = "INFORMATION_UPDATE"


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


@dataclass(frozen=True)
class ThreadDeletePlan:
    """Immutable snapshot required to resume a Thread deletion."""

    before_state: str


@dataclass(frozen=True)
class ThreadUpdatePlan:
    """Explicit command and frozen snapshots for project mutations."""

    command: str
    event_id: str
    actor: str
    timestamp: str
    before_state: str
    after_state: str


@dataclass(frozen=True)
class InformationCreatePlan:
    """Complete frozen Memory and deterministic Event/command metadata."""

    event_id: str
    after_state: str
    actor: str
    timestamp: str
    command_fingerprint: str


@dataclass(frozen=True)
class InformationUpdatePlan(InformationCreatePlan):
    before_state: str


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
    plan: (ThreadStatusChangePlan | ThreadCreatePlan | ThreadDeletePlan | ThreadUpdatePlan
           | InformationCreatePlan | InformationUpdatePlan | None) = None
    manual_resolutions: list[dict] = field(default_factory=list)

    def __post_init__(self) -> None:
        if (type(self.previous_revision) is not int or self.previous_revision < 0
                or type(self.revision) is not int or self.revision < 1):
            raise ValueError("Operation revisions must be non-negative integers")
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
        if self.operation_type is OperationType.THREAD_DELETE and (
            self.previous_revision < 1 or not isinstance(self.plan, ThreadDeletePlan)
        ):
            raise ValueError("THREAD_DELETE requires an existing Thread snapshot")

        if self.operation_type is OperationType.THREAD_UPDATE and (
            self.previous_revision < 1 or type(self.plan) is not ThreadUpdatePlan
        ):
            raise ValueError("THREAD_UPDATE requires an existing Thread and command")

        if self.operation_type is OperationType.INFORMATION_CREATE and (
            self.previous_revision != 0 or type(self.plan) is not InformationCreatePlan
        ):
            raise ValueError("INFORMATION_CREATE requires revision 1 and a creation plan")
        if self.operation_type is OperationType.INFORMATION_UPDATE and (
            self.previous_revision < 1 or type(self.plan) is not InformationUpdatePlan
        ):
            raise ValueError("INFORMATION_UPDATE requires an existing Information snapshot")


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
