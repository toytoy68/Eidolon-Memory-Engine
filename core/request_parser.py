"""JSON parsing for Eidolon request envelopes."""

from __future__ import annotations

import json
from typing import Any

from .requests import RequestEnvelope


def parse_request(data: str | bytes) -> RequestEnvelope:
    """Parse a JSON request envelope."""
    try:
        payload = json.loads(data)
    except (TypeError, json.JSONDecodeError) as exc:
        raise ValueError(f"Invalid request JSON: {exc}") from exc

    if not isinstance(payload, dict):
        raise ValueError("Request JSON must be an object.")

    if "request" not in payload:
        raise ValueError("Field request is missing.")

    request = payload["request"]

    if not isinstance(request, dict):
        raise ValueError("Field request must be an object.")

    required = ("schema_version", "domain", "intent")

    missing = [
        field
        for field in required
        if field not in request
    ]

    if missing:
        raise ValueError(
            "Request fields missing: " + ", ".join(missing)
        )

    filters = request.get("filters", {})

    if not isinstance(filters, dict):
        raise ValueError("Request filters must be an object.")

    return RequestEnvelope(
        schema_version=request["schema_version"],
        domain=request["domain"],
        intent=request["intent"],
        filters=filters,
    )
