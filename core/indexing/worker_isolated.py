"""Experimental upsert-only worker for a disposable index.

No delete, no journal transition, no live filesystem path. The caller supplies
trusted canonical and authorization callbacks. This cannot provide an atomic
snapshot across Markdown and Qdrant: it must not be used in production.
"""
from __future__ import annotations
from dataclasses import dataclass
from core.backend.models import Memory
from .reconcile_plan import Action, Canonical
from .worker_gate import check_upsert


@dataclass(frozen=True)
class UpsertResult:
    state: str
    information_id: str
    revision: int


def run_isolated_upsert(action: Action, *, index, read_canonical, authorize,
                        profile_id: str, model_id: str, expected_profile_id: str,
                        expected_model_id: str, expected_sha256: str):
    """Perform one bounded experimental upsert; never delete or mark indexed.

    read_canonical(id) returns (Memory, canonical file SHA-256). It MUST
    independently verify the file identity, revision and byte hash.
    authorize(profile_id, id) returns an exact bool from a trusted policy.
    """
    if disposable_test is not True:
        raise ValueError("isolated worker requires explicit disposable test mode")
    if (type(action) is not Action or action.kind not in ("INDEX_UPSERT", "ENQUEUE_UPSERT")
            or not callable(read_canonical) or not callable(authorize)
            or not hasattr(index, "upsert")):
        raise ValueError("unsupported worker operation")
    memory, digest = read_canonical(action.information_id)
    if (type(memory) is not Memory or memory.information_id != action.information_id
            or type(memory.revision) is not int or type(digest) is not str):
        raise ValueError("untrusted canonical snapshot")
    permission = authorize(profile_id, action.information_id)
    if type(permission) is not bool:
        raise ValueError("invalid authorization decision")
    gate = check_upsert(action, canonical=Canonical(memory.revision, digest),
                        profile_id=profile_id, model_id=model_id, permitted=permission,
                        expected_model_id=expected_model_id, expected_profile_id=expected_profile_id,
                        expected_revision=action.revision, expected_sha256=expected_sha256)
    if not gate.verified:
        return UpsertResult("BLOCKED", action.information_id, action.revision)
    # Re-read immediately before the effect; a changed revision/digest blocks.
    latest, latest_digest = read_canonical(action.information_id)
    if (type(latest) is not Memory or latest.information_id != action.information_id
            or latest.revision != memory.revision or latest_digest != digest
            or authorize(profile_id, action.information_id) is not True):
        return UpsertResult("BLOCKED", action.information_id, action.revision)
    try:
        index.upsert(latest)
    except Exception:
        # An ambiguous timeout might have applied: never claim success or retry blindly.
        return UpsertResult("UNCERTAIN", action.information_id, action.revision)
    return UpsertResult("APPLIED_UNCONFIRMED", action.information_id, action.revision)
