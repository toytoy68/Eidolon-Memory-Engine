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


def _flag(value):
    """A tri-state fact: exactly True, exactly False, or unknown (None or anything ambiguous)."""
    return value if type(value) is bool else None


def _seconds(value):
    try:
        return type(value) in (int, float) and math.isfinite(value)
    except OverflowError:                 # an int too large for a float (G266-7): not a usable time
        return False


def _audit(value):
    return (type(value) is str and value.strip() == value and 1 <= len(value) <= 256
            and value.isprintable())


def classify(facts, *, now, grace_seconds, keep_failed_for_review=True, epoch_window=None, not_before=None):
    """One verdict per generation. Any unknown, ambiguous or contradictory fact keeps the generation.

    epoch_window=(floor, ceiling) lets the host refuse a clock in another unit (milliseconds, dates);
    not_before is the latest clock this host already used: a regressed clock is refused.
    """
    if not _seconds(now) or now < 0:
        raise ValueError("invalid clock")
    if epoch_window is not None:
        if (type(epoch_window) is not tuple or len(epoch_window) != 2
                or not all(_seconds(x) for x in epoch_window) or not 0 <= epoch_window[0] < epoch_window[1]):
            raise ValueError("invalid epoch window")
        if not epoch_window[0] <= now <= epoch_window[1]:
            raise ValueError("implausible clock")
    if not_before is not None and (not _seconds(not_before) or now < not_before):
        raise ValueError("clock regressed")
    if not _seconds(grace_seconds) or grace_seconds <= 0:
        raise ValueError("a positive host-supplied grace period is required")
    facts = tuple(facts)  # a generator must not be consumed by the first pass
    if any(not isinstance(f, GenerationFacts) for f in facts):
        raise ValueError("invalid generation facts")
    names = [f.name for f in facts if type(f.name) is str]
    if len(set(names)) != len(names):
        raise ValueError("duplicate generation")
    # Alias state is judged per alias: one alias's target says nothing about another alias.
    alias_ok = {}
    for alias in {f.alias for f in facts if type(f.alias) is str}:
        group = [f for f in facts if f.alias == alias]
        alias_ok[alias] = (sum(_flag(f.is_alias_target) is True for f in group) == 1
                           and all(_flag(f.is_alias_target) is not None for f in group))
    out = []
    for f in facts:
        reasons = []
        if (type(f.alias) is not str or not f.alias or type(f.name) is not str
                or not re.fullmatch(re.escape(f.alias) + r"__[0-9a-f]{32}", f.name)):
            out.append(RetentionVerdict(str(f.name), "KEEP_UNCERTAIN", ("FOREIGN_OR_MALFORMED_NAME",)))
            continue
        if _flag(f.is_alias_target) is True:
            out.append(RetentionVerdict(f.name, "KEEP_ACTIVE", ("ALIAS_TARGET",)))
            continue
        if not alias_ok[f.alias]:
            reasons.append("ALIAS_STATE_UNCERTAIN")
        if _flag(f.descriptor_valid) is None or _flag(f.complete) is None:
            reasons.append("EVIDENCE_UNKNOWN")
        if reasons:
            out.append(RetentionVerdict(f.name, "KEEP_UNCERTAIN", tuple(reasons)))
            continue
        if type(f.readers) is not int or f.readers != 0:
            out.append(RetentionVerdict(f.name, "KEEP_READERS",
                                        ("READERS_ACTIVE",) if type(f.readers) is int and f.readers > 0
                                        else ("READERS_UNKNOWN",)))
            continue
        if not f.descriptor_valid or not f.complete:
            # A failed/partial build has no retirement history: a human must look at it.
            verdict = "REVIEW_CANDIDATE" if keep_failed_for_review is False else "KEEP_FAILED_EVIDENCE"
            out.append(RetentionVerdict(f.name, verdict, ("FAILED_OR_PARTIAL_BUILD",)))
            continue
        if not _seconds(f.retired_at) or f.retired_at < 0 or not _audit(f.audit_reference):
            out.append(RetentionVerdict(f.name, "KEEP_UNCERTAIN", ("RETIREMENT_NOT_PROVEN",)))
            continue
        if f.retired_at > now:
            out.append(RetentionVerdict(f.name, "KEEP_UNCERTAIN", ("RETIREMENT_IN_FUTURE",)))
            continue
        if epoch_window is not None and f.retired_at < epoch_window[0]:
            out.append(RetentionVerdict(f.name, "KEEP_UNCERTAIN", ("RETIREMENT_TIME_IMPLAUSIBLE",)))
            continue
        if now - f.retired_at < grace_seconds:  # the grace bound itself is inclusive: age == grace may go
            out.append(RetentionVerdict(f.name, "KEEP_RECENT", ("WITHIN_GRACE",)))
            continue
        out.append(RetentionVerdict(f.name, "REVIEW_CANDIDATE", ("RETIRED_COMPLETE_NO_READERS",)))
    return tuple(out)
