# ==========================================================
# Projet      : Eidolon Memory Engine
# Organisation: Eidolon Core Technologies (ECT)
# Fichier     : core/indexing/index_lag.py
# Description : Évaluateur pur du retard d'indexation (S1, G236-6), seuil fourni par l'hôte
# Standard    : Eidolon Presentation Standard v1
# ==========================================================
"""Pure index-lag evaluator (Claude, G236-6). No I/O, no clock read, no runtime activation.

The host supplies the current time, the pending intents (``ChangeIntent`` from ``ChangeJournal.pending``) and a
MANDATORY lag threshold it calibrated itself: this module invents no business threshold. Three causes stay
distinct and are never merged into one "stale" flag:

- index health: unavailable or incompatible (model / projection);
- canonical coverage: the canonical snapshot is incomplete or unknown;
- ageing: the oldest pending intent is older than the threshold.

``worker_status`` is not changed; a caller may show both summaries side by side.
"""
from dataclasses import dataclass
import math

STATES = ("INDEX_UNAVAILABLE", "INDEX_INCOMPATIBLE", "CANONICAL_INCOMPLETE", "INDEX_LAGGING",
          "INDEX_PENDING", "INDEX_CURRENT")


@dataclass(frozen=True)
class LagReport:
    state: str
    pending: int
    oldest_age_seconds: float | None
    lagging: int
    reasons: tuple


def _finite(value, name, *, positive=False):
    if type(value) not in (int, float) or not math.isfinite(value) or value < 0 or (positive and value == 0):
        raise ValueError(f"invalid {name}")
    return float(value)


def evaluate_lag(pending, *, now, threshold_seconds, index_available, index_compatible, canonical_complete,
                 clock_skew_seconds=60):
    """Classify index lag from host-supplied facts only.

    pending: iterable of objects with ``created`` (seconds since epoch, or None when unknown).
    An intent dated in the future beyond ``clock_skew_seconds`` makes ages untrustworthy: CLOCK_AHEAD is reported
    and no ageing verdict is given. A missing date is AGE_UNKNOWN, never "fresh".
    With unknown dates, oldest_age_seconds is unknown and lagging counts only known
    old intents: it is a lower bound, not an exhaustive count.
    """
    now = _finite(now, "clock")
    threshold = _finite(threshold_seconds, "lag threshold", positive=True)
    skew = _finite(clock_skew_seconds, "clock skew")
    if any(type(flag) is not bool for flag in (index_available, index_compatible, canonical_complete)):
        raise ValueError("invalid health flags")
    ages, reasons, count = [], set(), 0
    for intent in pending:
        count += 1
        created = getattr(intent, "created", None)
        if created is None:
            reasons.add("AGE_UNKNOWN")
            continue
        created = _finite(created, "intent timestamp")
        if created > now + skew:
            reasons.add("CLOCK_AHEAD")
            continue
        ages.append(max(0.0, now - created))
    clock_trusted = "CLOCK_AHEAD" not in reasons
    oldest = max(ages) if ages and clock_trusted and "AGE_UNKNOWN" not in reasons else None
    lagging = sum(age > threshold for age in ages) if clock_trusted else 0
    if not index_available:
        state = "INDEX_UNAVAILABLE"
    elif not index_compatible:
        state = "INDEX_INCOMPATIBLE"
    elif not canonical_complete:
        state = "CANONICAL_INCOMPLETE"
    elif lagging:
        state = "INDEX_LAGGING"
    elif count:
        state = "INDEX_PENDING"
    else:
        state = "INDEX_CURRENT"
    if lagging and state != "INDEX_LAGGING":
        reasons.add("ALSO_LAGGING")                    # health wins the state; ageing is still reported
    return LagReport(state, count, oldest, lagging, tuple(sorted(reasons)))
