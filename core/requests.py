# ==========================================================
# Projet      : Eidolon Memory Engine
# Organisation: Eidolon Core Technologies (ECT)
# Fichier     : core/requests.py
# Description : External request envelope for Eidolon Memory Engine.
# Standard    : Eidolon Presentation Standard v1
# ==========================================================

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

        if not isinstance(self.domain, str) or not self.domain:
            raise ValueError("Request domain must be nonempty text.")

        if not isinstance(self.intent, str) or not self.intent:
            raise ValueError("Request intent must be nonempty text.")

        if not isinstance(self.filters, dict):
            raise ValueError("Request filters must be an object.")
