"""Experimental trusted-entrypoint access facade.

This is NOT an authorization boundary against code able to access the raw
backend, filesystem, or SQLite index. The Principal must come from verified
server-side authentication, never an untrusted request field. Test only.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from core.backend.errors import MemoryNotFound
from core.backend.models import Memory


@dataclass(frozen=True)
class Principal:
    user_id: str

    def __post_init__(self) -> None:
        if not isinstance(self.user_id, str) or not self.user_id.strip():
            raise PermissionError("authenticated principal required")


class AuthorizedMemory:
    """Deny-by-default facade for a trusted in-process caller."""

    def __init__(self, backend: Any, principal: Principal) -> None:
        self._backend = backend
        self.principal = principal

    def _require_owner(self, memory: Memory | None) -> Memory:
        if memory is None or memory.metadata.get("owner") != self.principal.user_id:
            raise MemoryNotFound("memory not found or access denied")
        return memory

    def get(self, information_id: str) -> Memory:
        return self._require_owner(self._backend.get(information_id))

    def store(self, memory: Memory) -> Any:
        self._require_owner(memory)
        return self._backend.store(memory)

    def list(
        self,
        offset: int = 0,
        limit: int = 100,
        filters: dict[str, Any] | None = None,
    ) -> list[Memory]:
        if offset < 0 or limit < 1:
            raise ValueError("invalid pagination")
        records = self._backend.list(limit=1_000_000)
        allowed = [
            m for m in records if m.metadata.get("owner") == self.principal.user_id
        ]
        if filters:
            allowed = [
                m for m in allowed
                if self._backend._matches_filters(m, filters)
            ]
        return allowed[offset:offset + limit]

    def search(self, query: str, options: dict[str, Any] | None = None) -> list[Any]:
        # Searches the raw backend before filtering; leaks through untrusted
        # code or side channels remain possible. Do not deploy as a security boundary.
        candidates = self._backend.search(query, {"limit": 10_000})
        limit = max(1, min(10_000, int((options or {}).get("limit", 100))))
        return [
            x for x in candidates
            if x.memory.metadata.get("owner") == self.principal.user_id
        ][:limit]

    def update(self, information_id: str, memory: Memory, revision: int) -> Any:
        self.get(information_id)
        self._require_owner(memory)
        return self._backend.update(information_id, memory, revision)

    def delete_request(
        self,
        information_id: str,
        requested_by: str,
        reason: str,
        revision: int,
        operation_id: str,
    ) -> Any:
        self.get(information_id)
        if requested_by != self.principal.user_id:
            raise PermissionError("requester does not match principal")
        return self._backend.delete_request(
            information_id, requested_by, reason, revision, operation_id
        )

    def approve_delete(self, information_id: str, operation_id: str) -> Any:
        self.get(information_id)
        return self._backend.approve_delete(information_id, operation_id)

    def cancel_delete(self, information_id: str, operation_id: str) -> Any:
        self.get(information_id)
        return self._backend.cancel_delete(information_id, operation_id)
