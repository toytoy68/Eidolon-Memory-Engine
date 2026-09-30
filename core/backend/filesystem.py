"""Filesystem implementation of the Memory Backend."""

from __future__ import annotations

import json
import hashlib
import os
import re
from pathlib import Path
from typing import Any
from dataclasses import asdict, replace
from core.storage_format import encode_document, decode_document

from core.persistence import serialized_write, atomic_write_text, exclusive_write, has_symlink_component
from core.information.references import ensure_no_thread_links, ensure_no_information_links
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

        if (has_symlink_component(self.persistent_root)
                or has_symlink_component(self.pending_delete_root)):
            raise InvalidMemory("Information storage directory is a symlink")
        self.persistent_root.mkdir(parents=True, exist_ok=True)
        self.pending_delete_root.mkdir(parents=True, exist_ok=True)
        if (has_symlink_component(self.persistent_root)
                or has_symlink_component(self.pending_delete_root)):
            raise InvalidMemory("Information storage directory is a symlink")

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

    def _ensure_relations_do_not_reuse_deleted_identity(self, memory: Memory) -> None:
        """A receipt reserves its Information identity, including for new links.

        Called under the Persistent writer lock, shared with deletion decisions.
        Other targets may represent non-Information objects and remain allowed.
        """
        if not isinstance(memory.relations, list):
            return
        for relation in memory.relations:
            if not isinstance(relation, dict):
                continue
            for target in (relation.get("target_id"), relation.get("target")):
                if not isinstance(target, str) or not re.fullmatch(r"[A-Za-z0-9._-]+", target):
                    continue
                receipt = self.pending_delete_root / f"{target}.json"
                if receipt.is_symlink():
                    raise InvalidMemory("relation target deletion receipt is a symlink")
                target_path = self.persistent_root / f"{target}.md"
                if receipt.exists() and (target_path.is_symlink() or not target_path.is_file()):
                    raise RevisionConflict("relation targets a reserved Information identity")

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
        if revision_value < 1:
            raise InvalidMemory("invalid revision")

        content_match = re.search(
            r"## Content\s+(.*?)(?:\n---|\Z)",
            text,
            flags=re.DOTALL,
        )

        content = ""
        if content_match:
            content = content_match.group(1).strip()

        sections = {
            name: cls._extract_json_block(text, name)
            for name in ("Metadata", "Provenance", "Temporal", "Verification")
        }
        if any(not isinstance(value, dict) for value in sections.values()):
            raise InvalidMemory("invalid legacy Information object section")
        relations = cls._extract_json_block(text, "Relations")
        if not isinstance(relations, list):
            raise InvalidMemory("invalid legacy Information relations")

        return Memory(
            information_id=information_id,
            revision=revision_value,
            content=content,
            metadata=sections["Metadata"],
            provenance=sections["Provenance"],
            temporal=sections["Temporal"],
            verification=sections["Verification"],
            relations=relations,
        )

    # ------------------------------------------------------------------
    # Atomic filesystem operations
    # ------------------------------------------------------------------

    @staticmethod
    def _atomic_write(path: Path, content: str) -> None:
        atomic_write_text(path, content)

    # ------------------------------------------------------------------
    # Backend contract
    # ------------------------------------------------------------------

    @serialized_write("persistent_root")
    def store(self, memory: Memory) -> StoreResult:
        self._validate_id(memory.information_id)

        if type(memory.revision) is not int or memory.revision < 1:
            raise InvalidMemory("revision must be an integer >= 1")

        path = self._path(memory.information_id)

        if path.exists() or path.is_symlink():
            raise MemoryAlreadyExists(memory.information_id)

        receipt = self.pending_delete_root / f"{memory.information_id}.json"
        if receipt.is_symlink():
            raise InvalidMemory("deletion receipt is a symlink")
        if receipt.exists():
            raise RevisionConflict("deletion history reserves Information identity")

        self._ensure_relations_do_not_reuse_deleted_identity(memory)

        self._atomic_write(path, self._serialize(memory))

        return StoreResult(
            information_id=memory.information_id,
            revision=memory.revision,
        )

    def get(self, information_id: str) -> Memory | None:
        path = self._path(information_id)

        if path.is_symlink():
            raise InvalidMemory("Information path is a symlink")
        if not path.exists():
            return None

        try:
            memory = self._deserialize(path.read_text(encoding="utf-8"))
            if memory.information_id != information_id:
                raise InvalidMemory("Information identity does not match filename")
            return memory
        except (OSError, UnicodeError) as exc:
            raise InvalidMemory(
                f"unable to read memory: {information_id}"
            ) from exc

    def exists(self, information_id: str) -> bool:
        path = self._path(information_id)
        if path.is_symlink():
            raise InvalidMemory("Information path is a symlink")
        return path.exists()

    @serialized_write("persistent_root")
    def update(
        self,
        information_id: str,
        memory: Memory,
        previous_revision: int,
    ) -> UpdateResult:
        if type(previous_revision) is not int or previous_revision < 1:
            raise InvalidMemory("previous_revision must be an integer >= 1")
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
        updated = replace(memory, revision=new_revision)

        self._ensure_relations_do_not_reuse_deleted_identity(updated)

        self._atomic_write(
            self._path(information_id),
            self._serialize(updated),
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
        if (not isinstance(requested_by, str) or not requested_by
                or not isinstance(reason, str) or not reason
                or not isinstance(operation_id, str) or not operation_id
                or type(revision) is not int or revision < 1):
            raise InvalidMemory("invalid deletion request fields")
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

        if path.is_symlink() or path.exists():
            current_request = self._load_delete_request(path, information_id)
            if current_request["status"] == "PENDING_DELETE":
                if current_request == request:
                    return DeleteResult(information_id, "PENDING_DELETE")
                raise RevisionConflict("another deletion request is pending")
            if current_request["status"] in {"DELETED", "APPLYING_DELETE"}:
                raise RevisionConflict("previous deletion requires review")

        self._atomic_write(
            path,
            self._json(request) + "\n",
        )

        return DeleteResult(
            information_id=information_id,
            status="PENDING_DELETE",
        )

    @staticmethod
    def _load_delete_request(path: Path, information_id: str) -> dict:
        if path.is_symlink():
            raise InvalidMemory("pending delete request is a symlink")
        try:
            def unique_object(pairs):
                result = {}
                for key, value in pairs:
                    if key in result:
                        raise ValueError("duplicate deletion receipt key")
                    result[key] = value
                return result

            def invalid_constant(value):
                raise ValueError("invalid deletion receipt constant")

            request = json.loads(path.read_text(encoding="utf-8"),
                                 object_pairs_hook=unique_object,
                                 parse_constant=invalid_constant)
        except (OSError, UnicodeError, ValueError) as exc:
            raise InvalidMemory("pending delete request is unreadable") from exc
        receipt_fields = {"information_id", "requested_by", "reason", "revision",
                          "operation_id", "status", "content_sha256"}
        if (not isinstance(request, dict)
                or not request.keys() <= receipt_fields
                or request.get("information_id") != information_id
                or request.get("status") not in {"PENDING_DELETE", "APPLYING_DELETE", "CANCELLED", "DELETED"}
                or type(request.get("revision")) is not int or request["revision"] < 1
                or not isinstance(request.get("operation_id"), str)
                or not request["operation_id"]
                or not isinstance(request.get("requested_by"), str)
                or not request["requested_by"]
                or not isinstance(request.get("reason"), str)
                or not request["reason"]
                or ("content_sha256" in request
                    and (not isinstance(request["content_sha256"], str)
                         or not re.fullmatch(r"[0-9a-f]{64}", request["content_sha256"])))
                or (request.get("status") == "APPLYING_DELETE"
                    and "content_sha256" not in request)
                or (request.get("status") in {"PENDING_DELETE", "CANCELLED"}
                    and "content_sha256" in request)):
            raise InvalidMemory("pending delete request is invalid or has an identity mismatch")
        return request

    @serialized_write("persistent_root")
    def approve_delete(
        self,
        information_id: str,
        operation_id: str,
    ) -> DeleteResult:
        self._validate_id(information_id)
        request_path = self.pending_delete_root / f"{information_id}.json"

        if request_path.is_symlink():
            raise InvalidMemory("pending delete request is a symlink")
        if not request_path.exists():
            raise MemoryNotFound(
                f"pending delete request not found: {information_id}"
            )

        request = self._load_delete_request(request_path, information_id)

        if request.get("operation_id") != operation_id:
            raise RevisionConflict(
                "operation_id does not match pending delete request"
            )

        if request.get("status") not in {"PENDING_DELETE", "APPLYING_DELETE"}:
            raise RevisionConflict("deletion request is not pending")

        threads_root = self.persistent_root / "threads"
        if threads_root.is_symlink():
            raise InformationDeletionBlocked("Thread directory is a symlink")
        threads_root.mkdir(parents=True, exist_ok=True)
        with exclusive_write(threads_root):
            ensure_no_thread_links(threads_root, information_id)
            ensure_no_information_links(self.persistent_root, information_id,
                                        self._deserialize)
            memory_path = self._path(information_id)
            if memory_path.is_symlink():
                raise InvalidMemory("Information file is a symlink")
            if request["status"] == "PENDING_DELETE":
                current = self.get(information_id)
                if current is None:
                    raise MemoryNotFound(information_id)
                if current.revision != request["revision"]:
                    raise RevisionConflict("memory changed since deletion was requested")
                content_hash = hashlib.sha256(memory_path.read_bytes()).hexdigest()
                request["content_sha256"] = content_hash
                request["status"] = "APPLYING_DELETE"
                self._atomic_write(request_path, self._json(request) + "\n")
            if memory_path.exists():
                if hashlib.sha256(memory_path.read_bytes()).hexdigest() != request["content_sha256"]:
                    raise RevisionConflict("Information changed during deletion")
                memory_path.unlink()
                # Persist the directory update before recording completion.
                descriptor = os.open(memory_path.parent, os.O_RDONLY)
                try:
                    os.fsync(descriptor)
                finally:
                    os.close(descriptor)

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

        if request_path.is_symlink():
            raise InvalidMemory("pending delete request is a symlink")
        if not request_path.exists():
            raise MemoryNotFound(
                f"pending delete request not found: {information_id}"
            )

        request = self._load_delete_request(request_path, information_id)

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

    def _iter_valid_memories(self):
        """Yield readable, correctly named Information documents in path order."""
        for path in sorted(self.persistent_root.glob("*.md")):
            if path.is_symlink():
                continue
            try:
                memory = self._deserialize(
                    path.read_text(encoding="utf-8")
                )
            except (OSError, UnicodeError, InvalidMemory):
                continue
            if memory.information_id != path.stem:
                continue
            yield memory

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

        memories: list[Memory] = []
        skipped = 0

        for memory in self._iter_valid_memories():

            if filters and not self._matches_filters(memory, filters):
                continue

            if skipped < offset:
                skipped += 1
                continue
            memories.append(memory)
            if len(memories) == limit:
                break

        return memories

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
        if not isinstance(query, str):
            raise ValueError("query must be text")
        if options is not None and (not isinstance(options, dict)
                                    or options.keys() - {"limit", "offset", "ranking"}):
            raise ValueError("invalid search options")

        limit = 100
        offset = 0
        ranking = options.get("ranking", "legacy") if options else "legacy"
        if not isinstance(ranking, str) or ranking not in {"legacy", "lexical_v1"}:
            raise ValueError("unknown search ranking")

        if options and "limit" in options:
            limit = options["limit"]
            if type(limit) is not int or limit < 1:
                raise ValueError("limit must be a positive integer")
        if options and "offset" in options:
            offset = options["offset"]
            if type(offset) is not int or offset < 0:
                raise ValueError("offset must be a nonnegative integer")

        if not query:
            return []

        query_terms = [
            term.lower()
            for term in re.findall(r"\w+", query, flags=re.UNICODE)
        ]

        if not query_terms:
            return []

        results: list[SearchResult] = []

        if ranking == "lexical_v1":
            from core.retrieval.ranking import lexical_ranking
            for memory in self._iter_valid_memories():
                ranked = lexical_ranking(query, memory.content,
                                         memory.information_id, memory.metadata,
                                         (memory.provenance, memory.temporal,
                                          memory.verification, memory.relations))
                if ranked.coverage:
                    results.append(SearchResult(
                        memory=memory, score=ranked.score,
                        metadata={"ranking": ranked.explanation()},
                    ))
            results.sort(key=lambda result: (-result.score, result.memory.information_id))
            return results[offset:offset + limit]

        for memory in self._iter_valid_memories():
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

        return results[offset:offset + limit]

    def rebuild_index(self) -> dict[str, Any]:
        """Filesystem backend has no derived index yet."""

        return {
            "status": "NOT_REQUIRED",
            "indexed": 0,
            "backend": "filesystem",
        }
