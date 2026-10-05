#!/usr/bin/env python3

# ==========================================================
# Projet      : Eidolon Memory Engine
# Organisation: Eidolon Core Technologies (ECT)
# Fichier     : core/bootstrap.py
# Description : Module core — bootstrap
# Standard    : Eidolon Presentation Standard v1
# ==========================================================


from __future__ import annotations

import sys
from pathlib import Path


ENGINE_ROOT = Path(
    __file__
).resolve().parents[1]


if str(ENGINE_ROOT) not in sys.path:
    sys.path.insert(
        0,
        str(ENGINE_ROOT),
    )
