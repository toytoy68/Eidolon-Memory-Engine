# ==========================================================
# Projet      : Eidolon Memory Engine
# Organisation: Eidolon Core Technologies (ECT)
# Fichier     : core/threads/request_envelope.py
# Description : Mapping from external request envelopes to Thread requests.
# Standard    : Eidolon Presentation Standard v1
# ==========================================================

"""Mapping from external request envelopes to Thread requests."""

from __future__ import annotations

from core.requests import RequestEnvelope

from .models import ActionStatus, ThreadStatus
from .queries import ThreadQueryType, ThreadSortField, ThreadSortOrder
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

    filters = dict(envelope.filters)
    scalar_enums = {"status": ThreadStatus, "action_status": ActionStatus,
                    "sort_by": ThreadSortField, "sort_order": ThreadSortOrder}
    list_enums = {"statuses": ThreadStatus, "action_statuses": ActionStatus}
    try:
        for name, enum_type in scalar_enums.items():
            if name in filters and filters[name] is not None:
                filters[name] = enum_type(filters[name])
        for name, enum_type in list_enums.items():
            if name in filters:
                if not isinstance(filters[name], list):
                    raise ValueError("invalid status list")
                filters[name] = [enum_type(value) for value in filters[name]]
        request = ThreadRequest.from_intent(intent, **filters)
        request.query.validate()
        return request
    except (TypeError, ValueError) as exc:
        raise ValueError("Invalid Thread request filters") from exc
