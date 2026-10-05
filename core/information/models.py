# ==========================================================
# Projet      : Eidolon Memory Engine
# Organisation: Eidolon Core Technologies (ECT)
# Fichier     : core/information/models.py
# Description : Domain models for Eidolon Information.
# Standard    : Eidolon Presentation Standard v1
# ==========================================================

"""Domain models for Eidolon Information."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class InformationType(str, Enum):
    FACT = "FACT"
    OBSERVATION = "OBSERVATION"
    EVENT = "EVENT"
    HYPOTHESIS = "HYPOTHESIS"
    PREDICTION = "PREDICTION"
    INTERPRETATION = "INTERPRETATION"
    QUESTION = "QUESTION"
    DECISION = "DECISION"
    CONSTRAINT = "CONSTRAINT"
    PREFERENCE = "PREFERENCE"
    CONCEPT = "CONCEPT"
    PROCEDURE = "PROCEDURE"


class EpistemicStatus(str, Enum):
    UNKNOWN = "UNKNOWN"
    UNVERIFIED = "UNVERIFIED"
    CONFIRMED = "CONFIRMED"
    REFUTED = "REFUTED"
    CONFLICTED = "CONFLICTED"
    SUPERSEDED = "SUPERSEDED"


class OperationalState(str, Enum):
    ACTIVE = "ACTIVE"
    PLANNED = "PLANNED"
    PENDING_REVIEW = "PENDING_REVIEW"
    CANCELLED = "CANCELLED"
    COMPLETED = "COMPLETED"
    DEPRECATED = "DEPRECATED"


class Confidence(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class Importance(str, Enum):
    EPHEMERAL = "EPHEMERAL"
    LOW = "LOW"
    NORMAL = "NORMAL"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class Retention(str, Enum):
    PERMANENT = "PERMANENT"
    LONG_TERM = "LONG_TERM"
    NORMAL = "NORMAL"
    TEMPORARY = "TEMPORARY"
    DISPOSABLE = "DISPOSABLE"


@dataclass
class Information:
    """Canonical domain representation of a persistent Information object."""

    information_id: str
    content: str = ""
    revision: int = 1

    type: InformationType = InformationType.FACT
    epistemic_status: EpistemicStatus = EpistemicStatus.UNVERIFIED
    operational_state: OperationalState = OperationalState.ACTIVE

    confidence: Confidence = Confidence.LOW
    importance: Importance = Importance.NORMAL

    context: dict[str, Any] = field(default_factory=dict)
    provenance: dict[str, Any] = field(default_factory=dict)
    evidence: dict[str, Any] = field(
        default_factory=lambda: {
            "supporting": [],
            "contradicting": [],
        }
    )
    time: dict[str, Any] = field(default_factory=dict)
    relations: list[dict[str, Any]] = field(default_factory=list)
    triggers: list[dict[str, Any]] = field(default_factory=list)

    retention: Retention = Retention.NORMAL
