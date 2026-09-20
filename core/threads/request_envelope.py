"""Mapping from external request envelopes to Thread requests."""

from __future__ import annotations

from core.requests import RequestEnvelope

from .queries import ThreadQueryType
from .requests import ThreadRequest


def build_thread_request(envelope: RequestEnvelope) -> ThreadRequest:
    """Build a ThreadRequest from an external request envelope."""
    if envelope.domain != "THREAD":
        raise ValueError(
            f"Unsupported Thread request domain: {envelope.domain!r}"
        )

    try:
        intent = ThreadQueryType(envelope.intent)
    except ValueError as exc:
        raise ValueError(
            f"Unsupported Thread request intent: {envelope.intent!r}"
        ) from exc

    return ThreadRequest.from_intent(
        intent,
        **envelope.filters,
    )
