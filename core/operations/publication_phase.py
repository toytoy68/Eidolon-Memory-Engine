# ==========================================================
# Projet      : Eidolon Memory Engine
# Organisation: Eidolon Core Technologies (ECT)
# Fichier     : core/operations/publication_phase.py
# Description : État de la phase de lecture stabilisée, module feuille (proposition Claude L1, G236-10)
# Standard    : Eidolon Presentation Standard v1
# ==========================================================
"""Leaf module (standard library only) shared by core.persistence and core.operations.read_phase.

Breaking the persistence <-> read_phase cycle: persistence publishes files and must invalidate a settled read
phase, while read_phase needs persistence's lock helpers. The phase state and its invalidation live here.
"""
from contextvars import ContextVar
import os
from pathlib import Path

_phase = ContextVar('settled_read_phase', default=None)


def invalidate_publication(path):
    phase = _phase.get()
    if phase is not None:
        destination = Path(os.path.abspath(path))
        if any(destination == root or root in destination.parents for root in phase['sources']):
            phase['readiness'] = None
