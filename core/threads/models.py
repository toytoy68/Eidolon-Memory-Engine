"""Domain models for Eidolon Threads."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ThreadStatus(str, Enum):
    """Lifecycle states of a Thread."""

    PROPOSED = "PROPOSED"
    VALIDATED = "VALIDATED"
    IMPLEMENTATION = "IMPLEMENTATION"
    TESTING = "TESTING"
    COMPLETED = "COMPLETED"
    PAUSED = "PAUSED"
    BLOCKED = "BLOCKED"
    CANCELLED = "CANCELLED"


class ActionStatus(str, Enum):
    """Lifecycle states of a Thread action."""

    PLANNED = "PLANNED"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    BLOCKED = "BLOCKED"
    CANCELLED = "CANCELLED"


@dataclass
class ThreadAction:
    """An action belonging to a Thread."""

    action_id: str
    description: str
    status: ActionStatus = ActionStatus.PLANNED
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class Thread:
    """Canonical in-memory representation of a Thread."""

    thread_id: str
    title: str
    objective: str
    status: ThreadStatus = ThreadStatus.PROPOSED

    revision: int = 1

    context: dict[str, Any] = field(default_factory=dict)
    actions: list[ThreadAction] = field(default_factory=list)
    relations: list[dict[str, Any]] = field(default_factory=list)

    created_at: str = ""
    updated_at: str = ""
    started_at: str | None = None
    completed_at: str | None = None

    provenance: dict[str, Any] = field(default_factory=dict)

    def get_action(self, action_id: str) -> ThreadAction | None:
        """Return an action by identifier."""
        for action in self.actions:
            if action.action_id == action_id:
                return action

        return None

    def has_action(self, action_id: str) -> bool:
        """Return whether an action exists."""
        return self.get_action(action_id) is not None
