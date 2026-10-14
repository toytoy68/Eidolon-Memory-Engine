"""Pure, fail-closed revalidation gate for a future index worker.

This returns evidence only, never authorization to execute and never touches
Markdown, Qdrant, filesystem or journal. A real worker must repeat these checks
immediately before committing an effect.
"""
from dataclasses import dataclass
import re
from .reconcile_plan import Action, Canonical


@dataclass(frozen=True)
class UpsertGate:
    information_id: str
    revision: int
    canonical_sha256: str
    model_id: str
    profile_id: str
    verified: bool


def check_upsert(action: Action, *, canonical: Canonical, profile_id: str,
                 model_id: str, permitted: bool, expected_revision: int,
                 expected_sha256: str) -> UpsertGate:
    if (type(action) is not Action or action.kind not in ("INDEX_UPSERT", "ENQUEUE_UPSERT")
            or type(action.information_id) is not str or not action.information_id
            or type(action.revision) is not int or action.revision < 1
            or (action.kind == "INDEX_UPSERT" and (type(action.sequence) is not int or action.sequence < 1))
            or (action.kind == "ENQUEUE_UPSERT" and action.sequence is not None)
            or type(expected_revision) is not int or expected_revision < 1
            or type(expected_sha256) is not str or re.fullmatch(r"[0-9a-f]{64}", expected_sha256) is None
            or type(profile_id) is not str or not profile_id
            or type(model_id) is not str or not model_id
            or type(permitted) is not bool or not isinstance(canonical, Canonical)
            or type(canonical.revision) is not int or canonical.revision < 1
            or type(canonical.sha256) is not str or re.fullmatch(r"[0-9a-f]{64}", canonical.sha256) is None):
        raise ValueError("invalid worker gate evidence")
    verified = (permitted and canonical.revision == expected_revision == action.revision
                and canonical.sha256 == expected_sha256)
    return UpsertGate(action.information_id, action.revision, canonical.sha256,
                      model_id, profile_id, verified)
