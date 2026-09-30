"""Validation rules for Eidolon Memory Events."""

from __future__ import annotations

from .models import Event, EventRelation, EventType, RelationType, StateTransition


def validate_event(event: Event) -> list[str]:
    errors: list[str] = []

    if not isinstance(event.event_id, str) or not event.event_id:
        errors.append("event_id invalide")

    if type(event.revision) is not int or event.revision < 1:
        errors.append("revision doit être un entier >= 1")

    if event.information_id is not None and (
        not isinstance(event.information_id, str) or not event.information_id
    ):
        errors.append("information_id invalide")
    if event.thread_id is not None and (
        not isinstance(event.thread_id, str) or not event.thread_id
    ):
        errors.append("thread_id invalide")

    if not isinstance(event.event_type, EventType):
        errors.append("event_type invalide")
        return errors
    if (not isinstance(event.relations, list)
            or any(not isinstance(relation, EventRelation)
                   or not isinstance(relation.type, RelationType)
                   or not isinstance(relation.target, str) or not relation.target
                   for relation in event.relations)):
        errors.append("relations invalides")

    if not isinstance(event.state_transition, StateTransition) or not isinstance(
        event.state_transition.before, dict
    ) or not isinstance(
        event.state_transition.after, dict
    ):
        errors.append("state_transition invalide")
        return errors

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

    elif event.event_type is EventType.CREATED and has_thread:
        if event.revision != 1:
            errors.append("CREATED Thread nécessite revision 1")
        if event.state_transition.before:
            errors.append("CREATED Thread nécessite un état avant vide")
        if "status" not in event.state_transition.after:
            errors.append("CREATED Thread nécessite status dans state_transition.after")

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
