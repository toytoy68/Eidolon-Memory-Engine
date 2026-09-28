"""Filesystem implementation of the Memory Backend."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any
from dataclasses import asdict
from core.storage_format import encode_document, decode_document

from core.persistence import serialized_write, durable_replace, exclusive_write
from core.information.references import ensure_no_thread_links
from core.backend.errors import InformationDeletionBlocked

from core.config import PERSISTENT_ROOT, HISTORY_ROOT, ensure_directories

from .interface import MemoryBackend
from .errors import (
    InvalidMemory,
    MemoryAlreadyExists,
    MemoryNotFound,
    RevisionConflict,
)
from .models import DeleteResult, Memory, SearchResult, StoreResult, UpdateResult


class FilesystemBackend(MemoryBackend):
    """Canonical Markdown-based filesystem backend."""

    def __init__(
        self,
        persistent_root: Path | None = None,
        history_root: Path | None = None,
    ) -> None:
        if persistent_root is None or history_root is None:
            ensure_directories()

        self.persistent_root = (
            Path(persistent_root)
            if persistent_root is not None
            else PERSISTENT_ROOT
        )

        self.history_root = (
            Path(history_root)
            if history_root is not None
            else HISTORY_ROOT
        )

        self.pending_delete_root = self.history_root / "pending-delete"

        self.persistent_root.mkdir(parents=True, exist_ok=True)
        self.pending_delete_root.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Paths
    # ------------------------------------------------------------------

    def _validate_id(self, information_id: str) -> None:
        if not information_id:
            raise InvalidMemory("information_id is required")

        if not re.fullmatch(r"[A-Za-z0-9._-]+", information_id):
            raise InvalidMemory(
                f"invalid information_id: {information_id!r}"
            )

    def _path(self, information_id: str) -> Path:
        self._validate_id(information_id)
        return self.persistent_root / f"{information_id}.md"

    # ------------------------------------------------------------------
    # Serialization
    # ------------------------------------------------------------------

    @staticmethod
    def _json(value: Any) -> str:
        return json.dumps(
            value,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )

    @classmethod
    def _serialize(cls, memory: Memory) -> str:
        return encode_document("Information", asdict(memory))

    @staticmethod
    def _extract_json_block(text: str, section: str) -> Any:
        pattern = (
            rf"## {re.escape(section)}\s+"
            r"```json\s+"
            r"(.*?)"
            r"\s*```\s*"
        )

        match = re.search(pattern, text, flags=re.DOTALL)

        if not match:
            return {}

        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError as exc:
            raise InvalidMemory(
                f"invalid JSON in section {section!r}"
            ) from exc

    @classmethod
    def _deserialize(cls, text: str) -> Memory:
        try:
            payload = decode_document(text, "Information")
            if payload is not None:
                if not isinstance(payload.get("information_id"), str):
                    raise ValueError("invalid Information identity")
                if type(payload.get("revision")) is not int or payload["revision"] < 1:
                    raise ValueError("invalid Information revision")
                for name in ("metadata", "provenance", "temporal", "verification"):
                    if not isinstance(payload.get(name), dict):
                        raise ValueError(f"invalid Information {name}")
                if not isinstance(payload.get("relations"), list):
                    raise ValueError("invalid Information relations")
                return Memory(**payload)
        except (KeyError, TypeError, ValueError) as exc:
            raise InvalidMemory("invalid Information document") from exc
        identity = re.search(
            r"^id:\s*(.+)$",
            text,
            flags=re.MULTILINE,
        )

        revision = re.search(
            r"^revision:\s*(\d+)$",
            text,
            flags=re.MULTILINE,
        )

        if not identity or not revision:
            raise InvalidMemory("missing identity information")

        information_id = identity.group(1).strip()

        try:
            revision_value = int(revision.group(1))
        except ValueError as exc:
            raise InvalidMemory("invalid revision") from exc

        content_match = re.search(
            r"## Content\s+(.*?)(?:\n---|\Z)",
            text,
            flags=re.DOTALL,
        )

        content = ""
        if content_match:
            content = content_match.group(1).strip()

        return Memory(
            information_id=information_id,
            revision=revision_value,
            content=content,
            metadata=cls._extract_json_block(text, "Metadata"),
            provenance=cls._extract_json_block(text, "Provenance"),
            temporal=cls._extract_json_block(text, "Temporal"),
            verification=cls._extract_json_block(text, "Verification"),
            relations=cls._extract_json_block(text, "Relations"),
        )

    # ------------------------------------------------------------------
    # Atomic filesystem operations
    # ------------------------------------------------------------------

    @staticmethod
    def _atomic_write(path: Path, content: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)

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

        durable_replace(temporary_path, path)

    # ------------------------------------------------------------------
    # Backend contract
    # ------------------------------------------------------------------

    @serialized_write("persistent_root")
    def store(self, memory: Memory) -> StoreResult:
        self._validate_id(memory.information_id)

        if memory.revision < 1:
            raise InvalidMemory("revision must be >= 1")

        path = self._path(memory.information_id)

        if path.exists():
            raise MemoryAlreadyExists(memory.information_id)

        self._atomic_write(path, self._serialize(memory))

        return StoreResult(
            information_id=memory.information_id,
            revision=memory.revision,
        )

    def get(self, information_id: str) -> Memory | None:
        path = self._path(information_id)

        if not path.exists():
            return None

        try:
            memory = self._deserialize(path.read_text(encoding="utf-8"))
            if memory.information_id != information_id:
                raise InvalidMemory("Information identity does not match filename")
            return memory
        except OSError as exc:
            raise InvalidMemory(
                f"unable to read memory: {information_id}"
            ) from exc

    def exists(self, information_id: str) -> bool:
        return self._path(information_id).exists()

    @serialized_write("persistent_root")
    def update(
        self,
        information_id: str,
        memory: Memory,
        previous_revision: int,
    ) -> UpdateResult:
        current = self.get(information_id)

        if current is None:
            raise MemoryNotFound(information_id)

        if current.revision != previous_revision:
            raise RevisionConflict(
                f"{information_id}: expected revision "
                f"{previous_revision}, current revision "
                f"{current.revision}"
            )

        if memory.information_id != information_id:
            raise InvalidMemory(
                "memory.information_id does not match information_id"
            )

        new_revision = current.revision + 1
        memory.revision = new_revision

        self._atomic_write(
            self._path(information_id),
            self._serialize(memory),
        )

        return UpdateResult(
            information_id=information_id,
            previous_revision=current.revision,
            revision=new_revision,
        )

    @serialized_write("persistent_root")
    def delete_request(
        self,
        information_id: str,
        requested_by: str,
        reason: str,
        revision: int,
        operation_id: str,
    ) -> DeleteResult:
        memory = self.get(information_id)

        if memory is None:
            raise MemoryNotFound(information_id)

        if memory.revision != revision:
            raise RevisionConflict(
                f"{information_id}: expected revision "
                f"{revision}, current revision "
                f"{memory.revision}"
            )

        request = {
            "information_id": information_id,
            "requested_by": requested_by,
            "reason": reason,
            "revision": revision,
            "operation_id": operation_id,
            "status": "PENDING_DELETE",
        }

        path = self.pending_delete_root / f"{information_id}.json"

        if path.is_symlink():
            raise InvalidMemory("pending delete request is a symlink")
        if path.exists():
            try:
                current_request = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, UnicodeError, json.JSONDecodeError) as exc:
                raise InvalidMemory("pending delete request is unreadable") from exc
            if (not isinstance(current_request, dict)
                    or current_request.get("information_id") != information_id
                    or current_request.get("status") not in {
                        "PENDING_DELETE", "CANCELLED", "DELETED",
                    }):
                raise InvalidMemory("pending delete request is invalid")
            if current_request["status"] == "PENDING_DELETE":
                if current_request == request:
                    return DeleteResult(information_id, "PENDING_DELETE")
                raise RevisionConflict("another deletion request is pending")
            if current_request["status"] == "DELETED":
                raise RevisionConflict("previous deletion requires review")

        self._atomic_write(
            path,
            self._json(request) + "\n",
        )

        return DeleteResult(
            information_id=information_id,
            status="PENDING_DELETE",
        )

    @serialized_write("persistent_root")
    def approve_delete(
        self,
        information_id: str,
        operation_id: str,
    ) -> DeleteResult:
        self._validate_id(information_id)
        request_path = self.pending_delete_root / f"{information_id}.json"

        if not request_path.exists():
            raise MemoryNotFound(
                f"pending delete request not found: {information_id}"
            )

        request = json.loads(
            request_path.read_text(encoding="utf-8")
        )

        if not isinstance(request, dict) or request.get("information_id") != information_id:
            raise InvalidMemory("pending delete request identity mismatch")

        if request.get("operation_id") != operation_id:
            raise RevisionConflict(
                "operation_id does not match pending delete request"
            )

        if request.get("status") != "PENDING_DELETE":
            raise RevisionConflict("deletion request is not pending")
        current = self.get(information_id)
        if current is None:
            raise MemoryNotFound(information_id)
        if current.revision != request.get("revision"):
            raise RevisionConflict("memory changed since deletion was requested")

        threads_root = self.persistent_root / "threads"
        if threads_root.is_symlink():
            raise InformationDeletionBlocked("Thread directory is a symlink")
        threads_root.mkdir(parents=True, exist_ok=True)
        with exclusive_write(threads_root):
            ensure_no_thread_links(threads_root, information_id)
            memory_path = self._path(information_id)

            if memory_path.exists():
                memory_path.unlink()

            request["status"] = "DELETED"

            self._atomic_write(
                request_path,
                self._json(request) + "\n",
            )

        return DeleteResult(
            information_id=information_id,
            status="DELETED",
        )

    @serialized_write("persistent_root")
    def cancel_delete(
        self,
        information_id: str,
        operation_id: str,
    ) -> DeleteResult:
        self._validate_id(information_id)
        request_path = self.pending_delete_root / f"{information_id}.json"

        if not request_path.exists():
            raise MemoryNotFound(
                f"pending delete request not found: {information_id}"
            )

        request = json.loads(
            request_path.read_text(encoding="utf-8")
        )

        if not isinstance(request, dict) or request.get("information_id") != information_id:
            raise InvalidMemory("pending delete request identity mismatch")

        if request.get("operation_id") != operation_id:
            raise RevisionConflict(
                "operation_id does not match pending delete request"
            )

        if request.get("status") != "PENDING_DELETE":
            raise RevisionConflict("deletion request is not pending")

        request["status"] = "CANCELLED"

        self._atomic_write(
            request_path,
            self._json(request) + "\n",
        )

        return DeleteResult(
            information_id=information_id,
            status="CANCELLED",
        )

    def list(
        self,
        offset: int = 0,
        limit: int = 100,
        filters: dict[str, Any] | None = None,
    ) -> list[Memory]:
        if offset < 0:
            raise ValueError("offset must be >= 0")

        if limit < 1:
            raise ValueError("limit must be >= 1")

        paths = sorted(self.persistent_root.glob("*.md"))

        memories: list[Memory] = []

        for path in paths:
            try:
                memory = self._deserialize(
                    path.read_text(encoding="utf-8")
                )
            except (OSError, InvalidMemory):
                continue

            if filters and not self._matches_filters(memory, filters):
                continue

            memories.append(memory)

        return memories[offset : offset + limit]

    @staticmethod
    def _matches_filters(
        memory: Memory,
        filters: dict[str, Any],
    ) -> bool:
        for key, expected in filters.items():
            if key in {"revision", "information_id"}:
                if getattr(memory, key) != expected:
                    return False
                continue

            if key in memory.metadata:
                if memory.metadata[key] != expected:
                    return False
                continue

            return False

        return True

    def search(
        self,
        query: str,
        options: dict[str, Any] | None = None,
    ) -> list[SearchResult]:
        if not query:
            return []

        limit = 100

        if options and "limit" in options:
            limit = max(1, int(options["limit"]))

        query_terms = [
            term.lower()
            for term in re.findall(r"\w+", query, flags=re.UNICODE)
        ]

        if not query_terms:
            return []

        results: list[SearchResult] = []

        for memory in self.list(limit=10_000):
            haystack = self._json(
                {
                    "id": memory.information_id,
                    "content": memory.content,
                    "metadata": memory.metadata,
                    "provenance": memory.provenance,
                    "temporal": memory.temporal,
                    "verification": memory.verification,
                    "relations": memory.relations,
                }
            ).lower()

            matches = sum(
                1
                for term in query_terms
                if term in haystack
            )

            if matches:
                score = matches / len(query_terms)

                results.append(
                    SearchResult(
                        memory=memory,
                        score=score,
                    )
                )

        results.sort(
            key=lambda result: result.score or 0.0,
            reverse=True,
        )

        return results[:limit]

    def rebuild_index(self) -> dict[str, Any]:
        """Filesystem backend has no derived index yet."""

        return {
            "status": "NOT_REQUIRED",
            "indexed": 0,
            "backend": "filesystem",
        }
