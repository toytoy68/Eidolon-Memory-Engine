"""Read-only worker preflight: validate reconciliation plans before any effect.

No Qdrant client, no journal transitions, no filesystem writes. An actual
worker must re-read canonical state and check profile permissions immediately
before executing each approved operation.
"""
from dataclasses import dataclass
from .reconcile_plan import Action

ALLOWED_PROPOSALS = frozenset({"INDEX_UPSERT", "ENQUEUE_UPSERT"})
REVIEW_ACTIONS = frozenset({"MARK_PUBLISHED", "INDEX_DELETE", "ENQUEUE_DELETE", "CLOSE_ABANDONED",
                            "INTEGRITY_ALERT", "CLOSE_SUPERSEDED"})
WAIT_ACTIONS = frozenset({"WAIT"})


@dataclass(frozen=True)
class WorkerPreflight:
    proposals: tuple
    review: tuple
    refused: tuple
    waiting: tuple = ()


def preflight(actions, *, allow_upsert=False):
    """Classify untrusted plans; never grant execution authority.\n\n    Even with allow_upsert=True, callers must revalidate canonical state,\n    permissions and model identity before any effect. MARK_PUBLISHED is\n    journal state recovery, not an index operation.\n    """
    if type(allow_upsert) is not bool:
        raise ValueError("invalid preflight policy")
    proposals, review, refused, waiting = [], [], [], []
    for action in actions:
        if type(action) is not Action or type(action.information_id) is not str or not action.information_id:\n            raise ValueError("invalid reconciliation action")\n        if (type(action.kind) is not str or type(action.reason) is not str
                or type(action.revision) not in (int, type(None))
                or (action.revision is not None and action.revision < 1)
                or type(action.sequence) not in (int, type(None))
                or (action.sequence is not None and action.sequence < 1)):
            raise ValueError("invalid reconciliation action")
        kind = action.kind
        if kind in ALLOWED_PROPOSALS and (
                action.revision is None or
                (kind == "INDEX_UPSERT" and action.sequence is None) or
                (kind == "ENQUEUE_UPSERT" and action.sequence is not None)):
            raise ValueError("invalid upsert action provenance")
        if kind in ALLOWED_PROPOSALS:
            if allow_upsert:
                proposals.append(action)
            else:
                refused.append(action)
        elif kind in REVIEW_ACTIONS:
            review.append(action)
        elif kind in WAIT_ACTIONS:
            waiting.append(action)
        else:
            raise ValueError("unknown reconciliation action")
    return WorkerPreflight(tuple(proposals), tuple(review), tuple(refused), tuple(waiting))
