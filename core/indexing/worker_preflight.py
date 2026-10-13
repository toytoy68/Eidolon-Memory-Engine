"""Read-only worker preflight: validate reconciliation plans before any effect.

No Qdrant client, no journal transitions, no filesystem writes. An actual
worker must re-read canonical state and check profile permissions immediately
before executing each approved operation.
"""
from dataclasses import dataclass

ALLOWED_PROPOSALS = frozenset({"INDEX_UPSERT", "ENQUEUE_UPSERT", "MARK_PUBLISHED"})
REVIEW_ACTIONS = frozenset({"INDEX_DELETE", "ENQUEUE_DELETE", "CLOSE_ABANDONED",
                            "INTEGRITY_ALERT", "CLOSE_SUPERSEDED", "WAIT"})


@dataclass(frozen=True)
class WorkerPreflight:
    proposals: tuple
    review: tuple
    refused: tuple


def preflight(actions, *, allow_upsert=False):
    """Classify pure planner actions. Defaults to no executable proposals."""
    if type(allow_upsert) is not bool:
        raise ValueError("invalid preflight policy")
    proposals, review, refused = [], [], []
    for action in actions:
        kind = getattr(action, "kind", None)
        if kind in ALLOWED_PROPOSALS:
            if allow_upsert:
                proposals.append(action)
            else:
                refused.append(action)
        elif kind in REVIEW_ACTIONS:
            review.append(action)
        else:
            raise ValueError("unknown reconciliation action")
    return WorkerPreflight(tuple(proposals), tuple(review), tuple(refused))
