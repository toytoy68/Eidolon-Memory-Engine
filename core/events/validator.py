"""Validation rules for Eidolon Memory Events."""

from __future__ import annotations

from .models import Event, EventType


def validate_event(event: Event) -> list[str]:
    errors: list[str] = []

    if not event.event_id:
        errors.append("event_id vide")

    if event.revision < 1:
        errors.append("revision doit être >= 1")

    has_information = event.information_id is not None
    has_thread = event.thread_id is not None

    if has_information == has_thread:
        errors.append(
            "Un Event doit cibler exactement une Information ou un Thread"
        )

    if event.event_type is EventType.STATUS_CHANGED:
        if not has_thread:
            errors.append(
                "STATUS_CHANGED est réservé aux Events de Thread"
            )

        before = event.state_transition.before
        after = event.state_transition.after

        if "status" not in before:
            errors.append(
                "STATUS_CHANGED nécessite status dans state_transition.before"
            )

        if "status" not in after:
            errors.append(
                "STATUS_CHANGED nécessite status dans state_transition.after"
            )

    else:
        if not has_information:
            errors.append(
                "Les Events d Information doivent cibler une Information"
            )

        before = event.state_transition.before
        after = event.state_transition.after

        if before and not (
            "epistemic_status" in before
            or "operational_state" in before
        ):
            errors.append(
                "state_transition.before doit contenir un état Information"
            )

        if after and not (
            "epistemic_status" in after
            or "operational_state" in after
        ):
            errors.append(
                "state_transition.after doit contenir un état Information"
            )

    return errors


def is_valid(event: Event) -> bool:
    return not validate_event(event)
