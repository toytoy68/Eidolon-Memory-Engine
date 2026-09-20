"""Dispatch external request envelopes to domain services."""

from __future__ import annotations

from core.requests import RequestEnvelope
from core.responses import ResponseEnvelope
from core.threads.service import ThreadService


class RequestDispatcher:
    """Dispatch versioned request envelopes to domain services."""

    def __init__(self, thread_service: ThreadService) -> None:
        self.thread_service = thread_service

    def execute(self, envelope: RequestEnvelope) -> ResponseEnvelope:
        """Execute a request envelope against its target domain."""
        if envelope.domain == "THREAD":
            data = self.thread_service.execute_envelope(envelope)
            return build_response(envelope, data)

        raise ValueError(
            f"Unsupported request domain: {envelope.domain!r}"
        )


def build_response(
    envelope: RequestEnvelope,
    data,
) -> ResponseEnvelope:
    """Build a successful response envelope."""
    return ResponseEnvelope(
        domain=envelope.domain,
        intent=envelope.intent,
        status="OK",
        data=data,
    )
