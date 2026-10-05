# ==========================================================
# Projet      : Eidolon Memory Engine
# Organisation: Eidolon Core Technologies (ECT)
# Fichier     : core/maintenance/window.py
# Description : Pure maintenance-window eligibility; never observe activity or execute a pass.
# Standard    : Eidolon Presentation Standard v1
# ==========================================================

"""Pure maintenance-window eligibility; never observe activity or execute a pass."""
from datetime import datetime, time, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


def _instant(value, name):
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f'{name} requires an aware datetime')
    return value.astimezone(timezone.utc)


def preview_window(*, at, last_activity, start, end, zone, minimum_idle_minutes):
    """Inspect an explicit activity timestamp, not lock/CPU/readiness state.

    Windows are local wall-clock intervals [start, end), optionally overnight.
    Idle duration is elapsed UTC time, including across DST transitions.
    """
    now = _instant(at, 'at')
    activity = _instant(last_activity, 'last_activity')
    if activity > now:
        raise ValueError('last_activity cannot be after at')
    if (not isinstance(start, time) or not isinstance(end, time)
            or start.tzinfo is not None or end.tzinfo is not None or start == end):
        raise ValueError('distinct local start/end times without timezone required')
    if type(minimum_idle_minutes) is not int or minimum_idle_minutes < 1:
        raise ValueError('positive integer minimum_idle_minutes required')
    if not isinstance(zone, str) or not zone.strip():
        raise ValueError('IANA timezone required')
    try:
        local = now.astimezone(ZoneInfo(zone))
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ValueError('unknown IANA timezone') from exc
    clock = local.timetz().replace(tzinfo=None)
    in_window = (start <= clock < end) if start < end else (clock >= start or clock < end)
    idle_seconds = (now-activity).total_seconds()
    reasons = []
    if not in_window:
        reasons.append('OUTSIDE_WINDOW')
    if idle_seconds < minimum_idle_minutes*60:
        reasons.append('ACTIVITY_RECENT')
    return dict(status='DEFERRED' if reasons else 'ELIGIBLE', reasons=reasons,
        at=local.isoformat(), timezone=zone, start=start.isoformat(), end=end.isoformat(),
        minimum_idle_minutes=minimum_idle_minutes, idle_seconds=idle_seconds,
        execution_performed=False)
