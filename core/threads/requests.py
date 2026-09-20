"""Request contracts for Eidolon Threads."""

from __future__ import annotations

from dataclasses import dataclass

from .queries import ThreadQuery, ThreadQueryType


@dataclass(frozen=True)
class ThreadRequest:
    """Deterministic request targeting the Thread domain."""

    intent: ThreadQueryType
    query: ThreadQuery
    domain: str = "THREAD"

    def __post_init__(self) -> None:
        if self.domain != "THREAD":
            raise ValueError(
                "ThreadRequest domain must be THREAD"
            )

        if self.intent != self.query.query_type:
            raise ValueError(
                "ThreadRequest intent must match query type"
            )
