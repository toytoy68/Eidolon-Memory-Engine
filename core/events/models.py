"""Domain models for Eidolon Memory Events."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class EventType(str, Enum):
    CREATED = "CREATED"
    UPDATED = "UPDATED"
    VERIFIED = "VERIFIED"
    REFUTED = "REFUTED"
    CONFLICT_DETECTED = "CONFLICT_DETECTED"
    CONFLICT_RESOLVED = "CONFLICT_RESOLVED"
    REACTIVATED = "REACTIVATED"
    REVIEW_REQUESTED = "REVIEW_REQUESTED"
    REVIEW_COMPLETED = "REVIEW_COMPLETED"
    SUPERSEDED = "SUPERSEDED"
    DEPRECATED = "DEPRECATED"
    ARCHIVED = "ARCHIVED"
    RESTORED = "RESTORED"
    DELETED = "DELETED"
    STATUS_CHANGED = "STATUS_CHANGED"


class CauseType(str, Enum):
    NEW_INFORMATION = "NEW_INFORMATION"
    USER_VALIDATION = "USER_VALIDATION"
    SYSTEM_VALIDATION = "SYSTEM_VALIDATION"
    ADMIN_VALIDATION = "ADMIN_VALIDATION"
    CONTRADICTION = "CONTRADICTION"
    TRIGGER = "TRIGGER"
    TIME = "TIME"
    HARDWARE_CHANGE = "HARDWARE_CHANGE"
    SOFTWARE_CHANGE = "SOFTWARE_CHANGE"
    MANUAL_ACTION = "MANUAL_ACTION"
    OTHER = "OTHER"


class ValidationMode(str, Enum):
    AUTOMATIC = "AUTOMATIC"
    HUMAN = "HUMAN"
    HYBRID = "HYBRID"


class ValidationStatus(str, Enum):
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    PENDING_REVIEW = "PENDING_REVIEW"


class RelationType(str, Enum):
    RELATES_TO = "RELATES_TO"
    CONCERNS = "CONCERNS"
    DERIVED_FROM = "DERIVED_FROM"
    SUPPORTS = "SUPPORTS"
    CONTRADICTS = "CONTRADICTS"
    CONFIRMS = "CONFIRMS"
    REFUTES = "REFUTES"
    DEPENDS_ON = "DEPENDS_ON"
    REQUIRES = "REQUIRES"
    USES = "USES"
    PRODUCES = "PRODUCES"
    CAUSES = "CAUSES"
    CAUSED_BY = "CAUSED_BY"
    PRECEDES = "PRECEDES"
    FOLLOWS = "FOLLOWS"
    REPLACES = "REPLACES"
    SUPERSEDES = "SUPERSEDES"
    PART_OF = "PART_OF"
    BELONGS_TO = "BELONGS_TO"
    ASSOCIATED_WITH = "ASSOCIATED_WITH"


@dataclass
class StateTransition:
    before: dict[str, Any] = field(default_factory=dict)
    after: dict[str, Any] = field(default_factory=dict)


@dataclass
class Cause:
    type: CauseType
    description: str = ""


@dataclass
class Evidence:
    supporting: list[Any] = field(default_factory=list)
    contradicting: list[Any] = field(default_factory=list)


@dataclass
class Provenance:
    source_type: str = ""
    source: str = ""
    actor: str = ""
    timestamp: str = ""


@dataclass
class Validation:
    mode: ValidationMode
    status: ValidationStatus


@dataclass
class EventRelation:
    type: RelationType
    target: str


@dataclass
class Event:
    event_id: str
    revision: int
    event_type: EventType
    information_id: str | None = None
    thread_id: str | None = None
    state_transition: StateTransition = field(default_factory=StateTransition)
    cause: Cause | None = None
    evidence: Evidence = field(default_factory=Evidence)
    provenance: Provenance | None = None
    validation: Validation | None = None
    relations: list[EventRelation] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.revision < 1:
            raise ValueError("revision doit être >= 1")

        has_information = self.information_id is not None
        has_thread = self.thread_id is not None

        if has_information == has_thread:
            raise ValueError(
                "Un Event doit cibler exactement une Information ou un Thread"
            )

        if self.event_type is EventType.STATUS_CHANGED and not has_thread:
            raise ValueError(
                "STATUS_CHANGED est réservé aux Events de Thread"
            )

        if self.event_type is not EventType.STATUS_CHANGED and not has_information:
            raise ValueError(
                "Les Events d Information doivent cibler une Information"
            )
