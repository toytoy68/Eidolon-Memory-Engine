"""Query models for Eidolon Threads."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime, timezone

from .models import ActionStatus, ThreadStatus


def parse_timestamp(value: str) -> datetime:
    """Interpret ISO dates/times without an offset as UTC for legacy records."""
    if not isinstance(value, str):
        raise ValueError("timestamp must be an ISO string")
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None:
        result = result.replace(tzinfo=timezone.utc)
    return result.astimezone(timezone.utc)


class ThreadQueryType(str, Enum):
    """Supported read-only Thread queries."""

    LIST_THREADS = "LIST_THREADS"
    LIST_OPEN_THREADS = "LIST_OPEN_THREADS"
    LIST_THREADS_BY_STATUS = "LIST_THREADS_BY_STATUS"
    GET_THREAD = "GET_THREAD"
    LIST_THREAD_ACTIONS = "LIST_THREAD_ACTIONS"
    LIST_OPEN_ACTIONS = "LIST_OPEN_ACTIONS"


class ThreadSortField(str, Enum):
    """Fields supported for Thread result ordering."""

    CREATED_AT = "created_at"
    UPDATED_AT = "updated_at"
    STARTED_AT = "started_at"
    TITLE = "title"
    REVISION = "revision"
    STATUS = "status"


class ThreadSortOrder(str, Enum):
    """Sort direction."""

    ASC = "ASC"
    DESC = "DESC"


@dataclass
class ThreadQuery:
    """Read-only query definition for Threads."""

    query_type: ThreadQueryType

    thread_id: str | None = None

    status: ThreadStatus | None = None
    statuses: list[ThreadStatus] = field(default_factory=list)

    title: str | None = None
    title_contains: str | None = None

    action_id: str | None = None
    action_status: ActionStatus | None = None
    action_statuses: list[ActionStatus] = field(default_factory=list)

    relation_type: str | None = None
    related_to: str | None = None

    provenance: dict[str, object] = field(default_factory=dict)

    created_after: str | None = None
    created_before: str | None = None

    updated_after: str | None = None
    updated_before: str | None = None

    started_after: str | None = None
    started_before: str | None = None

    include_completed: bool = False
    include_cancelled: bool = False

    sort_by: ThreadSortField = ThreadSortField.UPDATED_AT
    sort_order: ThreadSortOrder = ThreadSortOrder.DESC

    limit: int = 20
    offset: int = 0

    def validate(self) -> None:
        """Validate query consistency."""

        if not isinstance(self.query_type, ThreadQueryType):
            raise ValueError("invalid query_type")

        for field_name in ("created_after", "created_before", "updated_after", "updated_before",
                           "started_after", "started_before"):
            value = getattr(self, field_name)
            if value is not None:
                parse_timestamp(value)
        for flag in (self.include_completed, self.include_cancelled):
            if type(flag) is not bool:
                raise ValueError("inclusion flags must be booleans")
        if type(self.limit) is not int or type(self.offset) is not int:
            raise ValueError("pagination must use integers")
        if self.sort_by not in ThreadSortField or self.sort_order not in ThreadSortOrder:
            raise ValueError("invalid sort field or order")
        if self.limit < 1:
            raise ValueError("limit must be >= 1")

        if self.limit > 1000:
            raise ValueError("limit must be <= 1000")

        if self.offset < 0:
            raise ValueError("offset must be >= 0")

        if ((self.status is not None and not isinstance(self.status, ThreadStatus))
                or (self.action_status is not None
                    and not isinstance(self.action_status, ActionStatus))
                or not isinstance(self.statuses, list)
                or any(not isinstance(status, ThreadStatus) for status in self.statuses)
                or not isinstance(self.action_statuses, list)
                or any(not isinstance(status, ActionStatus) for status in self.action_statuses)):
            raise ValueError("status filters must be lists of status values")
        if not isinstance(self.provenance, dict) or any(
                not isinstance(key, str) for key in self.provenance):
            raise ValueError("provenance filter must be a mapping with text keys")

        if self.title is not None and (not isinstance(self.title, str) or not self.title.strip()):
            raise ValueError("title cannot be empty")

        if (self.title_contains is not None
                and (not isinstance(self.title_contains, str)
                     or not self.title_contains.strip())):
            raise ValueError("title_contains cannot be empty")

        for name in ("thread_id", "action_id", "relation_type", "related_to"):
            value = getattr(self, name)
            if value is not None and (not isinstance(value, str) or not value):
                raise ValueError(f"{name} must be nonempty text")

        if self.query_type == ThreadQueryType.GET_THREAD:
            if not self.thread_id:
                raise ValueError(
                    "thread_id is required for GET_THREAD"
                )

        if self.query_type == ThreadQueryType.LIST_THREADS_BY_STATUS:
            if self.status is None and not self.statuses:
                raise ValueError(
                    "status or statuses is required for "
                    "LIST_THREADS_BY_STATUS"
                )

        if self.action_id is not None and not self.thread_id:
            raise ValueError(
                "thread_id is required when action_id is specified"
            )

    def normalized_statuses(self) -> list[ThreadStatus]:
        """Return a unique combined status list."""

        result: list[ThreadStatus] = []

        if self.status is not None:
            result.append(self.status)

        for status in self.statuses:
            if status not in result:
                result.append(status)

        return result

    def normalized_action_statuses(self) -> list[ActionStatus]:
        """Return a unique combined action-status list."""

        result: list[ActionStatus] = []

        if self.action_status is not None:
            result.append(self.action_status)

        for status in self.action_statuses:
            if status not in result:
                result.append(status)

        return result
