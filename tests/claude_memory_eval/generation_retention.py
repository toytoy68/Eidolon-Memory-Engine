# ==========================================================
# Projet      : Eidolon Memory Engine
# Organisation: Eidolon Core Technologies (ECT)
# Fichier     : tests/claude_memory_eval/generation_retention.py
# Description : Classificateur pur EXPÉRIMENTAL de rétention des générations Qdrant (Claude, G252-7)
# Standard    : Eidolon Presentation Standard v1
# ==========================================================
"""EXPERIMENTAL, test-only. No Qdrant client, no delete/drop, no clock read. It classifies host-supplied facts
about each generation; the best outcome is REVIEW_CANDIDATE, a request for a human decision. Proposal:
Core docs/proposals/2026-10-15-generation-retention.md. Does not close G201 Q3."""
from dataclasses import dataclass
import math
import re

VERDICTS = ("KEEP_ACTIVE", "KEEP_UNCERTAIN", "KEEP_READERS", "KEEP_RECENT", "KEEP_FAILED_EVIDENCE",
            "REVIEW_CANDIDATE")


@dataclass(frozen=True)
class GenerationFacts:
    name: str
    alias: str
    is_alias_target: bool | None          # None: alias state could not be read
    descriptor_valid: bool | None         # None: descriptor unreadable
    complete: bool | None                 # rebuild verified (count == manifest), None if unknown
    readers: int | None                   # active readers known to the host, None if unknown
    retired_at: float | None              # when it stopped being the alias target, from an audit log
    audit_reference: str | None           # id of the audit record proving that switch


@dataclass(frozen=True)
class RetentionVerdict:
    name: str
    verdict: str
    reasons: tuple


def classify(facts, *, now, grace_seconds, keep_failed_for_review=True):
    """One verdict per generation. Any unknown or contradictory fact keeps the generation."""
    if type(now) not in (int, float) or not math.isfinite(now) or now < 0:
        raise ValueError("invalid clock")
    if type(grace_seconds) not in (int, float) or not math.isfinite(grace_seconds) or grace_seconds <= 0:
        raise ValueError("a positive host-supplied grace period is required")
    out, targets = [], [f for f in facts if f.is_alias_target is True]
    names = [f.name for f in facts]
    if len(set(names)) != len(names):
        raise ValueError("duplicate generation")
    alias_ok = len(targets) == 1 and all(f.is_alias_target is not None for f in facts)
    for f in facts:
        reasons = []
        if not isinstance(f.name, str) or not re.fullmatch(re.escape(f.alias) + r"__[0-9a-f]{32}", f.name):
            out.append(RetentionVerdict(str(f.name), "KEEP_UNCERTAIN", ("FOREIGN_OR_MALFORMED_NAME",)))
            continue
        if f.is_alias_target is True:
            out.append(RetentionVerdict(f.name, "KEEP_ACTIVE", ("ALIAS_TARGET",)))
            continue
        if not alias_ok:
            reasons.append("ALIAS_STATE_UNCERTAIN")
        if f.descriptor_valid is None or f.complete is None:
            reasons.append("EVIDENCE_UNKNOWN")
        if reasons:
            out.append(RetentionVerdict(f.name, "KEEP_UNCERTAIN", tuple(reasons)))
            continue
        if f.readers is None or f.readers != 0:
            out.append(RetentionVerdict(f.name, "KEEP_READERS",
                                        ("READERS_UNKNOWN",) if f.readers is None else ("READERS_ACTIVE",)))
            continue
        if not f.descriptor_valid or not f.complete:
            # A failed/partial build has no retirement history: a human must look at it.
            verdict = "REVIEW_CANDIDATE" if keep_failed_for_review is False else "KEEP_FAILED_EVIDENCE"
            out.append(RetentionVerdict(f.name, verdict, ("FAILED_OR_PARTIAL_BUILD",)))
            continue
        if (f.retired_at is None or f.audit_reference is None or type(f.retired_at) not in (int, float)
                or not math.isfinite(f.retired_at) or f.retired_at > now):
            out.append(RetentionVerdict(f.name, "KEEP_UNCERTAIN", ("RETIREMENT_NOT_PROVEN",)))
            continue
        if now - f.retired_at < grace_seconds:
            out.append(RetentionVerdict(f.name, "KEEP_RECENT", ("WITHIN_GRACE",)))
            continue
        out.append(RetentionVerdict(f.name, "REVIEW_CANDIDATE", ("RETIRED_COMPLETE_NO_READERS",)))
    return tuple(out)
