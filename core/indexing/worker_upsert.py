"""Opt-in single-upsert worker, fail-closed and without delete support.

This module never loads credentials, opens canonical files, or selects an index.
Its trusted caller supplies a canonical reader and an authorization decision
callback. The reader is invoked immediately before the effect. A returned
success means only that the index adapter acknowledged the upsert; it does
not imply journal publication or end-to-end durability.
"""
from dataclasses import dataclass
from typing import Callable

from core.backend.models import Memory
from core.indexing.reconcile_plan import Action, Canonical
from core.indexing.worker_gate import check_upsert


@dataclass(frozen=True)
class UpsertReceipt:
    information_id: str
    revision: int
    state: str
    reason: str


def apply_upsert(action: Action, *, read_canonical: Callable, authorize: Callable,
                 index, profile_id: str, model_id: str, expected_model_id: str,
                 expected_profile_id: str, expected_sha256: str) -> UpsertReceipt:
    """Re-read, verify, then upsert; no delete, no implicit retries."""
    if (type(action) is not Action or action.kind not in ("INDEX_UPSERT", "ENQUEUE_UPSERT")
            or not callable(read_canonical) or not callable(authorize)
            or not callable(getattr(index, "upsert", None))):
        raise ValueError("invalid worker operation")
    if (type(expected_sha256) is not str or len(expected_sha256) != 64
            or any(ch not in "0123456789abcdef" for ch in expected_sha256)):
        raise ValueError("invalid expected canonical digest")
    # The canonical reader MUST verify the source bytes, identity and digest,
    # not simply return an untrusted index payload.
    observed = read_canonical(action.information_id)
    if (type(observed) is not tuple or len(observed) != 2
            or not isinstance(observed[0], Memory)
            or type(observed[1]) is not str):
        raise ValueError("canonical reader did not provide verified evidence")
    memory, digest = observed
    if memory.information_id != action.information_id:
        raise ValueError("canonical identity mismatch")
    permitted = authorize(profile_id, action.information_id, "index.upsert")
    if type(permitted) is not bool:
        raise ValueError("authorization must return a boolean")
    evidence = check_upsert(
        action, canonical=Canonical(memory.revision, digest),
        profile_id=profile_id, model_id=model_id, permitted=permitted,
        expected_model_id=expected_model_id, expected_profile_id=expected_profile_id,
        expected_revision=action.revision, expected_sha256=expected_sha256)
    if not evidence.verified:
        return UpsertReceipt(action.information_id, action.revision, "REFUSED",
                             "canonical, model, profile or authorization mismatch")
    # No retry on uncertain acknowledgements: caller must reconcile first.
    index.upsert(memory)
    # Recheck after an acknowledged write. A change detected here must not
    # advance the journal or be reported as a successful synchronization.
    # This is detection, NOT atomicity: a production writer lock is required.
    after = read_canonical(action.information_id)
    if (type(after) is not tuple or len(after) != 2
            or not isinstance(after[0], Memory) or type(after[1]) is not str
            or after[0].information_id != action.information_id
            or after[0].revision != memory.revision or after[1] != digest):
        return UpsertReceipt(action.information_id, action.revision, "STALE",
                             "canonical changed during index write; reconciliation required")
    still_permitted = authorize(profile_id, action.information_id, "index.upsert")
    if still_permitted is not True:
        return UpsertReceipt(action.information_id, action.revision, "STALE",
                             "permission changed during index write; reconciliation required")
    return UpsertReceipt(action.information_id, action.revision, "ACKNOWLEDGED",
                         "index adapter acknowledged; canonical rechecked; journal unchanged")
