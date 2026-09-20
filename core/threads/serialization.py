"""JSON-compatible serialization for Eidolon Threads."""

from __future__ import annotations

from typing import Any

from .models import Thread


def thread_to_dict(thread: Thread) -> dict[str, Any]:
    """Convert a Thread into a JSON-compatible dictionary."""
    return {
        "thread_id": thread.thread_id,
        "title": thread.title,
        "objective": thread.objective,
        "status": thread.status.value,
        "revision": thread.revision,
        "context": thread.context,
        "actions": [
            {
                "action_id": action.action_id,
                "description": action.description,
                "status": action.status.value,
                "metadata": action.metadata,
            }
            for action in thread.actions
        ],
        "relations": thread.relations,
        "created_at": thread.created_at,
        "updated_at": thread.updated_at,
        "started_at": thread.started_at,
        "completed_at": thread.completed_at,
        "provenance": thread.provenance,
    }


def thread_action_to_dict(action) -> dict[str, Any]:
    """Convert a ThreadAction into a JSON-compatible dictionary."""
    return {
        "action_id": action.action_id,
        "description": action.description,
        "status": action.status.value,
        "metadata": action.metadata,
    }


def serialize_thread_result(result) -> list[dict[str, Any]]:
    """Convert Thread query results into JSON-compatible data."""
    serialized = []

    for item in result:
        if isinstance(item, tuple):
            thread, action = item
            serialized.append(
                {
                    "thread": thread_to_dict(thread),
                    "action": thread_action_to_dict(action),
                }
            )
        else:
            serialized.append(thread_to_dict(item))

    return serialized
