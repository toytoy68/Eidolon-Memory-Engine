"""Dispatch external request envelopes to domain services."""

from __future__ import annotations

from core.requests import RequestEnvelope
from core.threads.service import ThreadService


class RequestDispatcher:
    """Dispatch versioned request envelopes to domain services."""

    def __init__(self, thread_service: ThreadService) -> None:
        self.thread_service = thread_service

    def execute(self, envelope: RequestEnvelope):
        """Execute a request envelope against its target domain."""
        if envelope.domain == "THREAD":
            return self.thread_service.execute_envelope(envelope)

        raise ValueError(
            f"Unsupported request domain: {envelope.domain!r}"
        )
