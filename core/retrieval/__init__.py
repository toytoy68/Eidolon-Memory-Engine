# ==========================================================
# Projet      : Eidolon Memory Engine
# Organisation: Eidolon Core Technologies (ECT)
# Fichier     : core/retrieval/__init__.py
# Description : Read-only context assembly from canonical Information search results.
# Standard    : Eidolon Presentation Standard v1
# ==========================================================

"""Read-only context assembly from canonical Information search results."""

from .context import ContextAssembler, ContextBundle, ContextItem

__all__ = ["ContextAssembler", "ContextBundle", "ContextItem"]
