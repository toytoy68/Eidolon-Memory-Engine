"""Opt-in single-upsert worker, fail-closed and without delete support.

This module never loads credentials, opens canonical files, or selects an index.
Its trusted caller supplies a canonical reader and an authorization decision
callback. The reader is invoked immediately before the effect. A returned
success means only that the index adapter acknowledged the upsert; it does
not imply journal publication or end-to-end durability.
"""
from dataclasses import dataclass
from pathlib import Path
from core.persistence import exclusive_write
from typing import Callable

from core.backend.models import Memory
from core.indexing.reconcile_plan import Action, Canonical
from core.indexing.worker_gate import check_upsert
from core.indexing.port import IndexEvidence


@dataclass(frozen=True)
class UpsertReceipt:
    information_id: str
    revision: int
    state: str
    reason: str


def _apply_unlocked(action: Action, *, read_canonical: Callable, authorize: Callable,
                 index, profile_id: str, model_id: str, expected_model_id: str,
                 expected_profile_id: str, expected_sha256: str) -> UpsertReceipt:
    """Re-read, verify, then upsert; no delete, no implicit retries."""
    if (type(action) is not Action or action.kind not in ("INDEX_UPSERT", "ENQUEUE_UPSERT")
            or not callable(read_canonical) or not callable(authorize)
            or not callable(getattr(index, "upsert_verified", None))):
        raise ValueError("invalid worker operation")
    if (type(expected_sha256) is not str or len(expected_sha256) != 64
            or any(ch not in "0123456789abcdef" for ch in expected_sha256)):
        raise ValueError("invalid expected canonical digest")
    # If the index exposes an embedding identity, never trust a caller's
    # model label over the adapter's own configured model.
    configured_model = getattr(index, "embedding_id", None)
    if configured_model is not None and configured_model != expected_model_id:
        return UpsertReceipt(action.information_id, action.revision, "REFUSED",
                             "index embedding identity differs from expected model")
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
    written = index.upsert_verified(memory, canonical_sha256=digest)
    # Acknowledgement is insufficient without point read-back.
    read_back = getattr(index, "evidence_for", None)
    if not callable(read_back):
        return UpsertReceipt(action.information_id, action.revision, "UNVERIFIED",
                             "index adapter has no point read-back")
    observed_point = read_back(action.information_id)
    if (type(written) is not IndexEvidence or type(observed_point) is not IndexEvidence
            or written != observed_point
            or written.information_id != memory.information_id
            or type(written.revision) is not int or written.revision != memory.revision
            or written.canonical_sha256 != digest
            or written.embedding_id != expected_model_id
            or type(written.generation) is not str or not written.generation):
        return UpsertReceipt(action.information_id, action.revision, "UNVERIFIED",
                             "index point provenance differs or is missing")
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


def apply_upsert(action: Action, *, read_canonical: Callable, authorize: Callable,
                 index, profile_id: str, model_id: str, expected_model_id: str,
                 expected_profile_id: str, expected_sha256: str,
                 canonical_root: Path | None = None) -> UpsertReceipt:
    """Hold the canonical writer lock throughout; no public unlocked fallback.

    Every writer must cooperate with the same lock. This remains an experimental
    single effect, not a journal transaction or a production service.
    """
    if canonical_root is None:
        raise ValueError("canonical_root required for worker")
    arguments = dict(read_canonical=read_canonical, authorize=authorize, index=index,
                     profile_id=profile_id, model_id=model_id,
                     expected_model_id=expected_model_id,
                     expected_profile_id=expected_profile_id,
                     expected_sha256=expected_sha256)
    root = Path(canonical_root)
    if not root.is_dir():
        raise ValueError("canonical root must be an existing directory")
    with exclusive_write(root):
        return _apply_unlocked(action, **arguments)


def apply_locked_upsert(action: Action, *, canonical_root: Path,
                        read_canonical: Callable, authorize: Callable,
                        index, profile_id: str, model_id: str,
                        expected_model_id: str, expected_profile_id: str,
                        expected_sha256: str) -> UpsertReceipt:
    """Explicit locked entrypoint; still experimental until production qualification."""
    if canonical_root is None:
        raise ValueError("canonical_root required for locked worker")
    return apply_upsert(action, canonical_root=canonical_root,
                        read_canonical=read_canonical, authorize=authorize,
                        index=index, profile_id=profile_id, model_id=model_id,
                        expected_model_id=expected_model_id,
                        expected_profile_id=expected_profile_id,
                        expected_sha256=expected_sha256)
