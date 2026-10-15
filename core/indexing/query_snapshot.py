# ==========================================================
# Projet      : Eidolon Memory Engine
# Organisation: Eidolon Core Technologies (ECT)
# Fichier     : core/indexing/query_snapshot.py
# Description : Optional query observation and canonical freshness diagnostics.
# Standard    : Eidolon Presentation Standard v1
# ==========================================================
"""Snapshot metadata is an observation, never a lease or a relevance proof."""
from dataclasses import dataclass

from core.indexing.port import IndexHit


@dataclass(frozen=True)
class IndexQuerySnapshot:
    hits: tuple[IndexHit, ...]
    generation: str
    source_digest: str | None


@dataclass(frozen=True)
class RecallIndexStatus:
    state: str
    reason: str
    generation: str | None = None
    source_digest: str | None = None
    canonical_digest: str | None = None
