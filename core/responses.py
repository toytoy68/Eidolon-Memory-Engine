"""External response envelope for Eidolon Memory Engine."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


SUPPORTED_SCHEMA = "0.1"

RESPONSE_STATUSES = (
    "OK",
    "ERROR",
)


@dataclass(frozen=True)
class ResponseEnvelope:
    """Versioned external response envelope."""

    domain: str
    intent: str
    status: str
    data: Any = field(default_factory=dict)
    schema_version: str = SUPPORTED_SCHEMA

    def __post_init__(self) -> None:
        if self.schema_version != SUPPORTED_SCHEMA:
            raise ValueError(
                f"Unsupported response schema: {self.schema_version!r}. "
                f"Expected: {SUPPORTED_SCHEMA}."
            )

        if not self.domain:
            raise ValueError("Response domain cannot be empty.")

        if not self.intent:
            raise ValueError("Response intent cannot be empty.")

        if self.status not in RESPONSE_STATUSES:
            raise ValueError(
                f"Unsupported response status: {self.status!r}."
            )
