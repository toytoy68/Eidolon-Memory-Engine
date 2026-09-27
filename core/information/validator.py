"""Validation rules for Eidolon Information."""

from __future__ import annotations

from .models import (
    EpistemicStatus,
    Information,
    InformationType,
    OperationalState,
)


def validate_information(information: Information) -> list[str]:
    """Return validation errors for an Information object."""
    errors: list[str] = []

    if not information.information_id:
        errors.append("id vide")

    if information.type not in InformationType:
        errors.append(f"type invalide : {information.type}")

    if information.epistemic_status not in EpistemicStatus:
        errors.append(
            f"epistemic_status invalide : {information.epistemic_status}"
        )

    if information.operational_state not in OperationalState:
        errors.append(
            f"operational_state invalide : {information.operational_state}"
        )

    return errors


def is_valid(information: Information) -> bool:
    """Return whether an Information object passes validation."""
    return not validate_information(information)
