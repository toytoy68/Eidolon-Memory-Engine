"""Read-only reconciliation preview; never mutates Markdown, journal or Qdrant.

Caller supplies independently verified canonical and index snapshots.
This module refuses inconsistent timestamps and avoids turning missing
index data into a deletion instruction.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
import time

from .change_journal import ChangeJournal
from .reconcile_plan import reconcile_plan


@dataclass(frozen=True)
class ReconcilePreview:
    actions: tuple
    pending_count: int
    generated_at: float
    requires_review: bool


def preview_reconciliation(journal: ChangeJournal, canonical: dict, indexed: dict,
                           *, now: float | None = None, grace_seconds: float = 600,
                           limit: int = 100):
    if not isinstance(journal, ChangeJournal):
        raise ValueError("journal required")
    reader = canonical if callable(canonical) else None
    if (reader is None and type(canonical) is not dict) or type(indexed) is not dict:
        raise ValueError("verified snapshots required")
    if type(limit) is not int or not 1 <= limit <= 999:
        raise ValueError("invalid limit")
    now = time.time() if now is None else now
    if type(now) not in (float, int) or not math.isfinite(now):
        raise ValueError("invalid clock")
    if type(grace_seconds) not in (float, int) or not math.isfinite(grace_seconds) or grace_seconds < 0:
        raise ValueError("invalid grace period")
    pending = journal.pending(limit=limit + 1)
    # Never treat a truncated journal as a complete snapshot.
    if len(pending) > limit:
        raise ValueError("pending journal may be truncated")
    ages = {}
    for intent in pending:
        if intent.created is not None:
            if not math.isfinite(intent.created) or intent.created > now:
                raise ValueError("invalid intent timestamp")
            ages[intent.sequence] = now - intent.created
    if reader is not None:
        canonical = reader(frozenset(indexed) | {intent.information_id for intent in pending})
        if type(canonical) is not dict:
            raise ValueError("verified snapshots required")
    actions = reconcile_plan(pending, canonical, indexed, ages=ages, grace_seconds=grace_seconds)
    unknown_ids = (set(indexed) | {intent.information_id for intent in pending}) - set(canonical)
    review = bool(unknown_ids) or any(action.kind in ("INTEGRITY_ALERT", "WAIT", "CLOSE_ABANDONED") for action in actions)
    return ReconcilePreview(actions, len(pending), float(now), review)
