#!/usr/bin/env python3

from __future__ import annotations

import os
from pathlib import Path

from core.persistence import has_symlink_component


# Racine du Memory Engine.
# Par défaut, elle est déterminée automatiquement
# depuis l'emplacement de ce fichier.
#
# Une variable MEMORY_ENGINE_ROOT peut toutefois
# imposer explicitement une autre racine.

_DEFAULT_ENGINE_ROOT = (
    Path(__file__).resolve().parents[1]
)

ENGINE_ROOT = Path(
    os.environ.get(
        "MEMORY_ENGINE_ROOT",
        str(_DEFAULT_ENGINE_ROOT),
    )
).resolve()


DATA_ROOT = ENGINE_ROOT / "memory"

WORKING_ROOT = DATA_ROOT / "working"
PERSISTENT_ROOT = DATA_ROOT / "persistent"
HISTORY_ROOT = DATA_ROOT / "history"

EVENTS_ROOT = HISTORY_ROOT / "events"
REVIEWS_ROOT = HISTORY_ROOT / "reviews"
OPERATIONS_ROOT = HISTORY_ROOT / "operations"

SCHEMAS_ROOT = ENGINE_ROOT / "schemas"
SERVICES_ROOT = ENGINE_ROOT / "services"


def ensure_directories() -> None:
    paths = (
        WORKING_ROOT,
        PERSISTENT_ROOT,
        EVENTS_ROOT,
        REVIEWS_ROOT,
        OPERATIONS_ROOT,
    )
    if any(has_symlink_component(path) for path in paths):
        raise ValueError("configured memory directory contains a symlink")
    for path in paths:
        path.mkdir(
            parents=True,
            exist_ok=True,
        )
    if any(has_symlink_component(path) for path in paths):
        raise ValueError("configured memory directory became a symlink")
