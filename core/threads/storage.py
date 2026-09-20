"""Persistent filesystem storage for Eidolon Threads."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from tempfile import NamedTemporaryFile

from .models import ActionStatus, Thread, ThreadAction, ThreadStatus


class ThreadStorageError(Exception):
    """Base exception for Thread storage operations."""


class InvalidThreadStorageId(ThreadStorageError):
    """Raised when a Thread identifier is invalid."""


class ThreadAlreadyExists(ThreadStorageError):
    """Raised when attempting to create an existing Thread."""


class ThreadStorage:
    """Canonical Markdown filesystem storage for Threads."""

    FORMAT_VERSION = "0.1"

    def __init__(self, persistent_root: Path) -> None:
        self.persistent_root = Path(persistent_root)
        self.threads_root = self.persistent_root / "threads"

        self.threads_root.mkdir(
            parents=True,
            exist_ok=True,
        )

    # ------------------------------------------------------------------
    # Paths
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_id(thread_id: str) -> None:
        if not thread_id:
            raise InvalidThreadStorageId(
                "thread_id is required"
            )

        if not re.fullmatch(
            r"[A-Za-z0-9._-]+",
            thread_id,
        ):
            raise InvalidThreadStorageId(
                f"invalid thread_id: {thread_id!r}"
            )

    def _path(self, thread_id: str) -> Path:
        self._validate_id(thread_id)

        return self.threads_root / f"{thread_id}.md"

    # ------------------------------------------------------------------
    # Serialization helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _json(value: object) -> str:
        return json.dumps(
            value,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )

    @classmethod
    def _serialize(cls, thread: Thread) -> str:
        actions = [
            {
                "action_id": action.action_id,
                "description": action.description,
                "status": action.status.value,
                "metadata": action.metadata,
            }
            for action in thread.actions
        ]

        temporal = {
            "created_at": thread.created_at,
            "updated_at": thread.updated_at,
            "started_at": thread.started_at,
            "completed_at": thread.completed_at,
        }

        lines = [
            "# Eidolon Thread Object",
            "",
            f"Version: {cls.FORMAT_VERSION}",
            "",
            "---",
            "",
            "## Identity",
            "",
            f"thread_id: {thread.thread_id}",
            f"revision: {thread.revision}",
            f"title: {thread.title}",
            f"status: {thread.status.value}",
            "",
            "---",
            "",
            "## Objective",
            "",
            thread.objective,
            "",
            "---",
            "",
            "## Context",
            "",
            "```json",
            cls._json(thread.context),
            "```",
            "",
            "---",
            "",
            "## Actions",
            "",
            "```json",
            cls._json(actions),
            "```",
            "",
            "---",
            "",
            "## Relations",
            "",
            "```json",
            cls._json(thread.relations),
            "```",
            "",
            "---",
            "",
            "## Temporal",
            "",
            "```json",
            cls._json(temporal),
            "```",
            "",
            "---",
            "",
            "## Provenance",
            "",
            "```json",
            cls._json(thread.provenance),
            "```",
            "",
        ]

        return "\n".join(lines)

    @staticmethod
    def _extract_json_block(
        text: str,
        section: str,
    ) -> object:
        pattern = (
            rf"## {re.escape(section)}\s+"
            r"```json\s+"
            r"(.*?)"
            r"\s*```\s*"
        )

        match = re.search(
            pattern,
            text,
            flags=re.DOTALL,
        )

        if not match:
            return {}

        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError as exc:
            raise ThreadStorageError(
                f"invalid JSON in section {section!r}"
            ) from exc

    @classmethod
    def _deserialize(cls, text: str) -> Thread:
        identity = re.search(
            r"^thread_id:\s*(.+)$",
            text,
            flags=re.MULTILINE,
        )

        revision = re.search(
            r"^revision:\s*(\d+)$",
            text,
            flags=re.MULTILINE,
        )

        title = re.search(
            r"^title:\s*(.*)$",
            text,
            flags=re.MULTILINE,
        )

        status = re.search(
            r"^status:\s*(.+)$",
            text,
            flags=re.MULTILINE,
        )

        if not identity or not revision or not title or not status:
            raise ThreadStorageError(
                "missing Thread identity information"
            )

        try:
            revision_value = int(revision.group(1))
        except ValueError as exc:
            raise ThreadStorageError(
                "invalid Thread revision"
            ) from exc

        try:
            status_value = ThreadStatus(status.group(1).strip())
        except ValueError as exc:
            raise ThreadStorageError(
                f"invalid Thread status: {status.group(1).strip()!r}"
            ) from exc

        objective_match = re.search(
            r"## Objective\s+(.*?)(?:\n---|\Z)",
            text,
            flags=re.DOTALL,
        )

        objective = ""
        if objective_match:
            objective = objective_match.group(1).strip()

        context = cls._extract_json_block(
            text,
            "Context",
        )

        actions_data = cls._extract_json_block(
            text,
            "Actions",
        )

        relations = cls._extract_json_block(
            text,
            "Relations",
        )

        temporal = cls._extract_json_block(
            text,
            "Temporal",
        )

        provenance = cls._extract_json_block(
            text,
            "Provenance",
        )

        if not isinstance(context, dict):
            raise ThreadStorageError(
                "Context must contain a JSON object"
            )

        if not isinstance(actions_data, list):
            raise ThreadStorageError(
                "Actions must contain a JSON array"
            )

        if not isinstance(relations, list):
            raise ThreadStorageError(
                "Relations must contain a JSON array"
            )

        if not isinstance(temporal, dict):
            raise ThreadStorageError(
                "Temporal must contain a JSON object"
            )

        if not isinstance(provenance, dict):
            raise ThreadStorageError(
                "Provenance must contain a JSON object"
            )

        actions: list[ThreadAction] = []

        for item in actions_data:
            if not isinstance(item, dict):
                raise ThreadStorageError(
                    "invalid action entry"
                )

            try:
                action = ThreadAction(
                    action_id=str(item["action_id"]),
                    description=str(item["description"]),
                    status=ActionStatus(item["status"]),
                    metadata=dict(item.get("metadata", {})),
                )
            except (KeyError, TypeError, ValueError) as exc:
                raise ThreadStorageError(
                    "invalid Thread action"
                ) from exc

            actions.append(action)

        thread = Thread(
            thread_id=identity.group(1).strip(),
            title=title.group(1).strip(),
            objective=objective,
            status=status_value,
            revision=revision_value,
            context=context,
            actions=actions,
            relations=relations,
            created_at=str(temporal.get("created_at", "")),
            updated_at=str(temporal.get("updated_at", "")),
            started_at=temporal.get("started_at"),
            completed_at=temporal.get("completed_at"),
            provenance=provenance,
        )

        return thread

    # ------------------------------------------------------------------
    # Atomic filesystem operations
    # ------------------------------------------------------------------

    @staticmethod
    def _atomic_write(
        path: Path,
        content: str,
    ) -> None:
        path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        with NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary_path = Path(handle.name)

            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())

        os.replace(
            temporary_path,
            path,
        )

    # ------------------------------------------------------------------
    # Basic storage operations
    # ------------------------------------------------------------------

    def create(self, thread: Thread) -> None:
        """Create a new persistent Thread."""

        self._validate_id(thread.thread_id)

        path = self._path(thread.thread_id)

        if path.exists():
            raise ThreadAlreadyExists(thread.thread_id)

        content = self._serialize(thread)

        self._atomic_write(
            path,
            content,
        )

    def get(self, thread_id: str) -> Thread | None:
        """Load a Thread by identifier."""

        path = self._path(thread_id)

        if not path.exists():
            return None

        text = path.read_text(
            encoding="utf-8",
        )

        return self._deserialize(text)

    def exists(self, thread_id: str) -> bool:
        """Return whether a Thread exists."""

        return self._path(thread_id).exists()
