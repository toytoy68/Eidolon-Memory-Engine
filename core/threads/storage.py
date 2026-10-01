"""Persistent filesystem storage for Eidolon Threads."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

from core.persistence import serialized_write, atomic_write_text, has_symlink_component

from core.storage_format import (encode_document, decode_document, decode_json_value,
                                 legacy_identity_fields)
from .serialization import thread_to_dict

from .models import ActionStatus, Thread, ThreadAction, ThreadStatus


class ThreadStorageError(Exception):
    """Base exception for Thread storage operations."""


class InvalidThreadStorageId(ThreadStorageError):
    """Raised when a Thread identifier is invalid."""


class ThreadAlreadyExists(ThreadStorageError):
    """Raised when attempting to create an existing Thread."""


class ThreadRevisionConflict(ThreadStorageError):
    """Raised when the persisted Thread revision has changed."""


class ThreadStorage:
    """Canonical Markdown filesystem storage for Threads."""

    FORMAT_VERSION = "0.2"

    def __init__(self, persistent_root: Path) -> None:
        self.persistent_root = Path(persistent_root)
        self.threads_root = self.persistent_root / "threads"

        if has_symlink_component(self.threads_root):
            raise ThreadStorageError("Thread directory is a symlink")
        self.threads_root.mkdir(
            parents=True,
            exist_ok=True,
        )
        if has_symlink_component(self.threads_root):
            raise ThreadStorageError("Thread directory is a symlink")

    # ------------------------------------------------------------------
    # Paths
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_id(thread_id: str) -> None:
        if not isinstance(thread_id, str) or not thread_id:
            raise InvalidThreadStorageId(
                "thread_id must be nonempty text"
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
        return encode_document("Thread", thread_to_dict(thread))

    @classmethod
    def _serialize_checked(cls, thread: Thread) -> str:
        """Reject values that would change or become unreadable on disk."""
        try:
            content = cls._serialize(thread)
            restored = cls._deserialize(content)
            if thread_to_dict(restored) != thread_to_dict(thread):
                raise ThreadStorageError("Thread changes during serialization")
            return content
        except (AttributeError, TypeError, ValueError) as exc:
            raise ThreadStorageError("invalid Thread document") from exc

    @staticmethod
    def _from_payload(data) -> Thread:
        if type(data.get("revision")) is not int or data["revision"] < 1:
            raise ValueError("invalid Thread revision")
        for name in ("thread_id", "title", "objective", "created_at", "updated_at"):
            if not isinstance(data.get(name), str):
                raise ValueError(f"invalid Thread {name}")
        for name in ("started_at", "completed_at"):
            if data.get(name) is not None and not isinstance(data[name], str):
                raise ValueError(f"invalid Thread {name}")
        for name in ("context", "provenance"):
            if not isinstance(data.get(name), dict):
                raise ValueError(f"invalid Thread {name}")
        for name in ("actions", "relations"):
            if not isinstance(data.get(name), list):
                raise ValueError(f"invalid Thread {name}")
        values = dict(data)
        values["status"] = ThreadStatus(values["status"])
        actions = []
        for item in values["actions"]:
            if (not isinstance(item, dict) or not isinstance(item.get("action_id"), str)
                    or not isinstance(item.get("description"), str)
                    or not isinstance(item.get("metadata"), dict)):
                raise ValueError("invalid Thread action")
            actions.append(ThreadAction(**dict(item, status=ActionStatus(item["status"]))))
        values["actions"] = actions
        return Thread(**values)

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
            return decode_json_value(match.group(1))
        except ValueError as exc:
            raise ThreadStorageError(
                f"invalid JSON in section {section!r}"
            ) from exc

    @classmethod
    def _deserialize(cls, text: str) -> Thread:
        try:
            payload = decode_document(text, "Thread")
            if payload is not None:
                return cls._from_payload(payload)
        except (KeyError, TypeError, ValueError) as exc:
            raise ThreadStorageError("invalid Thread document") from exc
        try:
            fields = legacy_identity_fields(text, ("thread_id", "revision", "title", "status"))
        except ValueError as exc:
            raise ThreadStorageError("missing or ambiguous Thread identity information") from exc

        try:
            if not re.fullmatch(r"[0-9]+", fields["revision"]):
                raise ValueError("invalid Thread revision")
            revision_value = int(fields["revision"])
        except ValueError as exc:
            raise ThreadStorageError(
                "invalid Thread revision"
            ) from exc
        if revision_value < 1:
            raise ThreadStorageError("invalid Thread revision")

        try:
            status_value = ThreadStatus(fields["status"].strip())
        except ValueError as exc:
            raise ThreadStorageError(
                f"invalid Thread status: {fields['status'].strip()!r}"
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
            thread_id=fields["thread_id"].strip(),
            title=fields["title"].strip(),
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
        atomic_write_text(path, content)

    # ------------------------------------------------------------------
    # Basic storage operations
    # ------------------------------------------------------------------

    @staticmethod
    def _concerns(thread: Thread) -> set[str]:
        targets = set()
        for relation in thread.relations:
            if not isinstance(relation, dict):
                raise ThreadStorageError("invalid Thread relation")
            if relation.get("type") != "CONCERNS":
                continue
            target = relation.get("target_id")
            legacy = relation.get("target")
            if (target is not None and legacy is not None and target != legacy):
                raise ThreadStorageError("ambiguous CONCERNS target")
            target = target if target is not None else legacy
            if not isinstance(target, str) or not re.fullmatch(r"[A-Za-z0-9._-]+", target):
                raise ThreadStorageError("invalid CONCERNS target")
            targets.add(target)
        return targets

    def _check_concerns(self, thread: Thread) -> None:
        # The persistent lock is held by create before checking any target.
        from core.backend.filesystem import FilesystemBackend
        from core.backend.errors import InvalidMemory

        for target in self._concerns(thread):
            path = self.persistent_root / f"{target}.md"
            if path.is_symlink() or not path.is_file():
                raise ThreadStorageError(f"missing linked Information: {target}")
            try:
                memory = FilesystemBackend._deserialize(path.read_text(encoding="utf-8"))
            except (OSError, UnicodeError, InvalidMemory) as exc:
                raise ThreadStorageError(f"unreadable linked Information: {target}") from exc
            if memory.information_id != target:
                raise ThreadStorageError(f"linked Information identity mismatch: {target}")

    @serialized_write("persistent_root")
    @serialized_write("threads_root")
    def create(self, thread: Thread) -> None:
        """Create a new persistent Thread."""

        self._validate_id(thread.thread_id)
        if type(thread.revision) is not int or thread.revision < 1:
            raise ThreadStorageError("Thread revision must be an integer >= 1")

        path = self._path(thread.thread_id)

        if path.exists() or path.is_symlink():
            raise ThreadAlreadyExists(thread.thread_id)

        self._check_concerns(thread)
        content = self._serialize_checked(thread)

        self._atomic_write(
            path,
            content,
        )

    def get(self, thread_id: str) -> Thread | None:
        """Load a Thread by identifier."""

        path = self._path(thread_id)

        if path.is_symlink():
            raise ThreadStorageError("Thread path is a symlink")
        if not path.exists():
            return None

        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            raise ThreadStorageError("unable to read Thread") from exc

        thread = self._deserialize(text)
        if thread.thread_id != thread_id:
            raise ThreadStorageError("Thread identity does not match filename")
        return thread

    def exists(self, thread_id: str) -> bool:
        """Return whether a Thread exists."""

        path = self._path(thread_id)
        if path.is_symlink():
            raise ThreadStorageError("Thread path is a symlink")
        return path.exists()

    @serialized_write("threads_root")
    def update(
        self,
        thread: Thread,
        previous_revision: int,
    ) -> None:
        """Update a Thread using optimistic revision control."""
        self._validate_id(thread.thread_id)
        if type(previous_revision) is not int:
            raise ThreadStorageError("previous_revision must be an integer")
        if type(thread.revision) is not int:
            raise ThreadStorageError("Thread revision must be an integer")

        current = self.get(thread.thread_id)

        if current is None:
            raise ThreadStorageError(
                f"Thread not found: {thread.thread_id}"
            )

        if current.revision != previous_revision:
            raise ThreadRevisionConflict(
                f"{thread.thread_id}: expected revision "
                f"{previous_revision}, current revision "
                f"{current.revision}"
            )

        expected_revision = previous_revision + 1

        if thread.revision != expected_revision:
            raise ThreadRevisionConflict(
                f"{thread.thread_id}: new revision must be "
                f"{expected_revision}, got {thread.revision}"
            )

        if self._concerns(current) != self._concerns(thread):
            raise ThreadStorageError("CONCERNS changes require a coordinated writer")

        content = self._serialize_checked(thread)

        self._atomic_write(
            self._path(thread.thread_id),
            content,
        )

    def _update_coordinated(self, before: Thread, after: Thread) -> None:
        """Internal publication under Persistent → Thread coordinator locks."""
        if (before.thread_id != after.thread_id or after.revision != before.revision + 1
                or self.get(before.thread_id) != before):
            raise ThreadRevisionConflict("Thread diverged before coordinated publication")
        self._check_concerns(after)
        self._atomic_write(self._path(after.thread_id), self._serialize_checked(after))

    def _delete_committed(self, thread_id: str) -> None:
        """Unlink only after a deletion operation reached APPLYING under the lock."""
        path = self._path(thread_id)

        if path.is_symlink():
            raise ThreadStorageError("Thread path is a symlink")
        if not path.exists():
            raise ThreadStorageError(
                f"Thread not found: {thread_id}"
            )

        path.unlink()
        descriptor = os.open(self.threads_root, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)

    def delete(self, thread_id: str, *, previous_revision: int | None = None,
               operation_id: str | None = None, coordinator=None) -> None:
        """Delete through an Operation journal; direct unlink is unavailable."""
        if previous_revision is None or operation_id is None:
            raise ThreadStorageError("previous_revision and operation_id are required for deletion")
        if coordinator is None:
            from core.operations.thread_delete import FilesystemThreadDeletion
            coordinator = FilesystemThreadDeletion.for_history(
                self, self.persistent_root.parent / "history")
        coordinator.delete(thread_id, previous_revision=previous_revision,
                           operation_id=operation_id)

    def list(self) -> list[Thread]:
        """Return all persisted Threads."""
        threads: list[Thread] = []

        for path in sorted(self.threads_root.glob("*.md")):
            if path.is_symlink():
                raise ThreadStorageError("Thread path is a symlink")
            try:
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeError) as exc:
                raise ThreadStorageError("unable to read Thread") from exc
            thread = self._deserialize(text)
            if thread.thread_id != path.stem:
                raise ThreadStorageError("Thread identity does not match filename")
            threads.append(thread)

        return threads
