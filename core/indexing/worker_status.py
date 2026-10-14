"""Pure diagnostic summary for an index worker. No filesystem or Qdrant effects."""
from dataclasses import dataclass
from .worker_prepare import PreparedWork


@dataclass(frozen=True)
class WorkerStatus:
    state: str
    candidates: int
    waiting: int
    review: int
    blocked: int


def summarize_work(prepared: PreparedWork, *, index_available: bool,
                   canonical_complete: bool, model_compatible: bool) -> WorkerStatus:
    if not isinstance(prepared, PreparedWork):
        raise ValueError("invalid prepared work")
    if any(type(x) is not bool for x in (index_available, canonical_complete, model_compatible)):
        raise ValueError("invalid status flags")
    all_entries = (prepared.candidate_ids, prepared.waiting_ids,
                   prepared.review_ids, prepared.blocked_ids)
    for entries in all_entries:
        if not isinstance(entries, tuple) or any(type(x) is not str or not x for x in entries):
            raise ValueError("invalid work entries")
    if not index_available:
        state = "INDEX_UNAVAILABLE"
    elif not model_compatible:
        state = "INDEX_INCOMPATIBLE"
    elif not canonical_complete:
        state = "INDEX_STALE"
    elif prepared.review_ids:
        state = "REVIEW_REQUIRED"
    elif prepared.waiting_ids or prepared.candidate_ids:
        state = "INDEX_PENDING"
    elif prepared.blocked_ids:
        state = "POLICY_BLOCKED"
    else:
        state = "INDEX_CURRENT"
    return WorkerStatus(state, len(prepared.candidate_ids), len(prepared.waiting_ids),
                        len(prepared.review_ids), len(prepared.blocked_ids))
