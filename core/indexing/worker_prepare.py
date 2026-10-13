"""Read-only worker preparation. This module never calls Qdrant or mutates files.

A proposal is NOT an authorization. A real worker must independently check
the current canonical revision, profile permissions and embedding version.
"""
from dataclasses import dataclass
from .worker_preflight import preflight


@dataclass(frozen=True)
class PreparedWork:
    candidate_ids: tuple[str, ...]
    review_ids: tuple[str, ...]
    blocked_ids: tuple[str, ...]
    waiting_ids: tuple[str, ...] = ()


def prepare_work(preview, *, allow_upsert=False):
    """Extract candidate document ids from a read-only reconciliation preview."""
    from .reconcile_preview import ReconcilePreview
    if not isinstance(preview, ReconcilePreview) or type(preview.requires_review) is not bool:
        raise ValueError("invalid preview")
    classified = preflight(preview.actions, allow_upsert=allow_upsert)
    # A preview requiring review cannot promote any action into a candidate.
    if preview.requires_review:
        return PreparedWork(
            (), tuple(a.information_id for a in classified.review),
            tuple(a.information_id for a in classified.refused + classified.proposals),
            tuple(a.information_id for a in classified.waiting))
    return PreparedWork(
        tuple(a.information_id for a in classified.proposals),
        tuple(a.information_id for a in classified.review),
        tuple(a.information_id for a in classified.refused),
        tuple(a.information_id for a in classified.waiting))
