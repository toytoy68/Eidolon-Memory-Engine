# ==========================================================
# Projet      : Eidolon Memory Engine
# Organisation: Eidolon Core Technologies (ECT)
# Fichier     : core/information/validator.py
# Description : Validation rules for Eidolon Information.
# Standard    : Eidolon Presentation Standard v1
# ==========================================================

"""Validation rules for Eidolon Information."""

from __future__ import annotations

from .models import (
    EpistemicStatus,
    Information,
    InformationType,
    OperationalState,
)


def _is_enum_value(value: object, enum_type: type) -> bool:
    """Accept a domain Enum member or its wire value on Python 3.11+."""
    return isinstance(value, enum_type) or (
        type(value) is str and value in {member.value for member in enum_type}
    )


def validate_information(information: Information) -> list[str]:
    """Return validation errors for an Information object."""
    errors: list[str] = []

    if not information.information_id:
        errors.append("id vide")

    if not _is_enum_value(information.type, InformationType):
        errors.append(f"type invalide : {information.type}")

    if not _is_enum_value(information.epistemic_status, EpistemicStatus):
        errors.append(
            f"epistemic_status invalide : {information.epistemic_status}"
        )

    if not _is_enum_value(information.operational_state, OperationalState):
        errors.append(
            f"operational_state invalide : {information.operational_state}"
        )

    return errors


def is_valid(information: Information) -> bool:
    """Return whether an Information object passes validation."""
    return not validate_information(information)
