"""Deterministic mapping from Thread requests to Thread queries."""

from __future__ import annotations

from .queries import ThreadQuery
from .requests import ThreadRequest


def build_thread_query(request: ThreadRequest) -> ThreadQuery:
    """Build the deterministic ThreadQuery carried by a request."""
    return request.query
