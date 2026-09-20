"""External request envelope for Eidolon Memory Engine."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


SUPPORTED_SCHEMA = "0.1"


@dataclass(frozen=True)
class RequestEnvelope:
    """Versioned external request envelope."""

    domain: str
    intent: str
    filters: dict[str, Any] = field(default_factory=dict)
    schema_version: str = SUPPORTED_SCHEMA

    def __post_init__(self) -> None:
        if self.schema_version != SUPPORTED_SCHEMA:
            raise ValueError(
                f"Unsupported request schema: {self.schema_version!r}. "
                f"Expected: {SUPPORTED_SCHEMA}."
            )

        if not self.domain:
            raise ValueError("Request domain cannot be empty.")

        if not self.intent:
            raise ValueError("Request intent cannot be empty.")

        if not isinstance(self.filters, dict):
            raise ValueError("Request filters must be an object.")
