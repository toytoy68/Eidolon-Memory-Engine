"""Business logic for Eidolon Threads."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone

from .models import ActionStatus, Thread, ThreadAction, ThreadStatus
from .queries import (
    ThreadQuery,
    ThreadQueryType,
    ThreadSortField,
    ThreadSortOrder,
)


class ThreadError(Exception):
    """Base exception for Thread operations."""


class InvalidThread(ThreadError):
    """Raised when a Thread is invalid."""


class InvalidThreadTransition(ThreadError):
    """Raised when a status transition is not allowed."""


class ActionNotFound(ThreadError):
    """Raised when an action does not exist."""


class DuplicateAction(ThreadError):
    """Raised when an action identifier already exists."""


class ThreadManager:
    """Manage Thread domain rules.

    Persistence is deliberately not implemented here yet.
    """

    ALLOWED_TRANSITIONS: dict[ThreadStatus, set[ThreadStatus]] = {
        ThreadStatus.PROPOSED: {
            ThreadStatus.VALIDATED,
            ThreadStatus.CANCELLED,
        },
        ThreadStatus.VALIDATED: {
            ThreadStatus.IMPLEMENTATION,
            ThreadStatus.PAUSED,
            ThreadStatus.BLOCKED,
            ThreadStatus.CANCELLED,
        },
        ThreadStatus.IMPLEMENTATION: {
            ThreadStatus.TESTING,
            ThreadStatus.PAUSED,
            ThreadStatus.BLOCKED,
            ThreadStatus.CANCELLED,
        },
        ThreadStatus.TESTING: {
            ThreadStatus.COMPLETED,
            ThreadStatus.IMPLEMENTATION,
            ThreadStatus.PAUSED,
            ThreadStatus.BLOCKED,
            ThreadStatus.CANCELLED,
        },
        ThreadStatus.PAUSED: {
            ThreadStatus.VALIDATED,
            ThreadStatus.IMPLEMENTATION,
            ThreadStatus.TESTING,
            ThreadStatus.CANCELLED,
        },
        ThreadStatus.BLOCKED: {
            ThreadStatus.VALIDATED,
            ThreadStatus.IMPLEMENTATION,
            ThreadStatus.TESTING,
            ThreadStatus.CANCELLED,
        },
        ThreadStatus.COMPLETED: set(),
        ThreadStatus.CANCELLED: set(),
    }

    @staticmethod
    def now_iso() -> str:
        """Return the current local ISO-8601 timestamp."""
        return datetime.now(timezone.utc).astimezone().isoformat(
            timespec="seconds"
        )

    @classmethod
    def validate(cls, thread: Thread) -> None:
        """Validate Thread invariants."""

        if not thread.thread_id:
            raise InvalidThread("thread_id is required")

        if not thread.title.strip():
            raise InvalidThread("title is required")

        if not thread.objective.strip():
            raise InvalidThread("objective is required")

        if thread.revision < 1:
            raise InvalidThread("revision must be >= 1")

        if not isinstance(thread.status, ThreadStatus):
            raise InvalidThread("invalid Thread status")

        if not thread.created_at:
            raise InvalidThread("created_at is required")

        if not thread.updated_at:
            raise InvalidThread("updated_at is required")

        if thread.completed_at and thread.status != ThreadStatus.COMPLETED:
            raise InvalidThread(
                "completed_at must be empty unless status is COMPLETED"
            )

        if thread.status == ThreadStatus.COMPLETED:
            if not thread.completed_at:
                raise InvalidThread(
                    "completed_at is required for COMPLETED Thread"
                )

        action_ids: set[str] = set()

        for action in thread.actions:
            if not action.action_id:
                raise InvalidThread("action_id is required")

            if not action.description.strip():
                raise InvalidThread(
                    f"action description is required: {action.action_id}"
                )

            if action.action_id in action_ids:
                raise InvalidThread(
                    f"duplicate action_id: {action.action_id}"
                )

            action_ids.add(action.action_id)

    @classmethod
    def change_status(
        cls,
        thread: Thread,
        new_status: ThreadStatus,
    ) -> Thread:
        """Apply a validated status transition."""

        cls.validate(thread)

        if thread.status == new_status:
            raise InvalidThreadTransition(
                f"Thread already has status {new_status.value}"
            )

        allowed = cls.ALLOWED_TRANSITIONS.get(
            thread.status,
            set(),
        )

        if new_status not in allowed:
            raise InvalidThreadTransition(
                f"invalid transition: "
                f"{thread.status.value} -> {new_status.value}"
            )

        now = cls.now_iso()

        updated = replace(
            thread,
            status=new_status,
            revision=thread.revision + 1,
            updated_at=now,
        )

        if new_status == ThreadStatus.IMPLEMENTATION:
            if updated.started_at is None:
                updated.started_at = now

        if new_status == ThreadStatus.COMPLETED:
            updated.completed_at = now

        cls.validate(updated)

        return updated

    @classmethod
    def add_action(
        cls,
        thread: Thread,
        action: ThreadAction,
    ) -> Thread:
        """Add an action to a Thread."""

        cls.validate(thread)

        if thread.status in {
            ThreadStatus.COMPLETED,
            ThreadStatus.CANCELLED,
        }:
            raise InvalidThread(
                "cannot add an action to a closed Thread"
            )

        if thread.has_action(action.action_id):
            raise DuplicateAction(action.action_id)

        actions = [
            *thread.actions,
            action,
        ]

        updated = replace(
            thread,
            actions=actions,
            revision=thread.revision + 1,
            updated_at=cls.now_iso(),
        )

        cls.validate(updated)

        return updated

    @classmethod
    def update_action_status(
        cls,
        thread: Thread,
        action_id: str,
        new_status: ActionStatus,
    ) -> Thread:
        """Change the status of an existing action."""

        cls.validate(thread)

        if thread.status in {
            ThreadStatus.COMPLETED,
            ThreadStatus.CANCELLED,
        }:
            raise InvalidThread(
                "cannot modify actions of a closed Thread"
            )

        action = thread.get_action(action_id)

        if action is None:
            raise ActionNotFound(action_id)

        updated_actions: list[ThreadAction] = []

        for current in thread.actions:
            if current.action_id == action_id:
                updated_actions.append(
                    replace(
                        current,
                        status=new_status,
                    )
                )
            else:
                updated_actions.append(current)

        updated = replace(
            thread,
            actions=updated_actions,
            revision=thread.revision + 1,
            updated_at=cls.now_iso(),
        )

        cls.validate(updated)

        return updated

    @classmethod
    def query(
        cls,
        threads: list[Thread],
        query: ThreadQuery,
    ) -> list[Thread] | list[tuple[Thread, ThreadAction]]:
        """Execute a read-only Thread query."""

        query.validate()

        if query.query_type == ThreadQueryType.GET_THREAD:
            return [
                thread
                for thread in threads
                if thread.thread_id == query.thread_id
            ]

        results = list(threads)

        if query.query_type == ThreadQueryType.LIST_OPEN_THREADS:
            results = [
                thread
                for thread in results
                if thread.status
                not in {
                    ThreadStatus.COMPLETED,
                    ThreadStatus.CANCELLED,
                }
            ]

        if query.query_type == ThreadQueryType.LIST_THREADS_BY_STATUS:
            statuses = set(query.normalized_statuses())
            results = [
                thread
                for thread in results
                if thread.status in statuses
            ]

        if query.title is not None:
            results = [
                thread
                for thread in results
                if thread.title == query.title
            ]

        if query.title_contains is not None:
            needle = query.title_contains.casefold()
            results = [
                thread
                for thread in results
                if needle in thread.title.casefold()
            ]

        if query.relation_type is not None:
            results = [
                thread
                for thread in results
                if any(
                    relation.get("type") == query.relation_type
                    for relation in thread.relations
                )
            ]

        if query.related_to is not None:
            results = [
                thread
                for thread in results
                if any(
                    relation.get("target_id") == query.related_to
                    or relation.get("source_id") == query.related_to
                    for relation in thread.relations
                )
            ]

        if query.provenance:
            results = [
                thread
                for thread in results
                if all(
                    thread.provenance.get(key) == value
                    for key, value in query.provenance.items()
                )
            ]

        if query.created_after is not None:
            results = [
                thread
                for thread in results
                if thread.created_at > query.created_after
            ]

        if query.created_before is not None:
            results = [
                thread
                for thread in results
                if thread.created_at < query.created_before
            ]

        if query.updated_after is not None:
            results = [
                thread
                for thread in results
                if thread.updated_at > query.updated_after
            ]

        if query.updated_before is not None:
            results = [
                thread
                for thread in results
                if thread.updated_at < query.updated_before
            ]

        if query.started_after is not None:
            results = [
                thread
                for thread in results
                if thread.started_at is not None
                and thread.started_at > query.started_after
            ]

        if query.started_before is not None:
            results = [
                thread
                for thread in results
                if thread.started_at is not None
                and thread.started_at < query.started_before
            ]

        if query.query_type == ThreadQueryType.LIST_OPEN_ACTIONS:
            action_statuses = set(
                query.normalized_action_statuses()
            )

            if not action_statuses:
                action_statuses = {
                    ActionStatus.PLANNED,
                    ActionStatus.IN_PROGRESS,
                    ActionStatus.BLOCKED,
                }

            action_results: list[tuple[Thread, ThreadAction]] = []

            for thread in results:
                for action in thread.actions:
                    if action.status in action_statuses:
                        action_results.append((thread, action))

            return action_results[
                query.offset : query.offset + query.limit
            ]

        if query.query_type == ThreadQueryType.LIST_THREAD_ACTIONS:
            action_results = []

            for thread in results:
                for action in thread.actions:
                    if query.action_id is not None:
                        if action.action_id != query.action_id:
                            continue

                    action_statuses = set(
                        query.normalized_action_statuses()
                    )

                    if action_statuses and action.status not in action_statuses:
                        continue

                    action_results.append((thread, action))

            return action_results[
                query.offset : query.offset + query.limit
            ]

        sort_key_map = {
            ThreadSortField.CREATED_AT: lambda thread: thread.created_at,
            ThreadSortField.UPDATED_AT: lambda thread: thread.updated_at,
            ThreadSortField.STARTED_AT: lambda thread: (
                thread.started_at or ""
            ),
            ThreadSortField.TITLE: lambda thread: thread.title.casefold(),
            ThreadSortField.REVISION: lambda thread: thread.revision,
            ThreadSortField.STATUS: lambda thread: thread.status.value,
        }

        sort_key = sort_key_map[query.sort_by]

        results.sort(
            key=sort_key,
            reverse=query.sort_order == ThreadSortOrder.DESC,
        )

        return results[
            query.offset : query.offset + query.limit
        ]
