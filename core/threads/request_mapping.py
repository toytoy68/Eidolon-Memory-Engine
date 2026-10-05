# ==========================================================
# Projet      : Eidolon Memory Engine
# Organisation: Eidolon Core Technologies (ECT)
# Fichier     : core/threads/request_mapping.py
# Description : Deterministic mapping from Thread requests to Thread queries.
# Standard    : Eidolon Presentation Standard v1
# ==========================================================

"""Deterministic mapping from Thread requests to Thread queries."""

from __future__ import annotations

from .queries import ThreadQuery
from .requests import ThreadRequest


def build_thread_query(request: ThreadRequest) -> ThreadQuery:
    """Build the deterministic ThreadQuery carried by a request."""
    return request.query
