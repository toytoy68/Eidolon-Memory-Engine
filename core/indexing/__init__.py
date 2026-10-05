# ==========================================================
# Projet      : Eidolon Memory Engine
# Organisation: Eidolon Core Technologies (ECT)
# Fichier     : core/indexing/__init__.py
# Description : Read-only foundations for derived indexes.
# Standard    : Eidolon Presentation Standard v1
# ==========================================================

"""Read-only foundations for derived indexes."""

from .manifest import IndexDelta, IndexManifest, SourceEntry, build_manifest, diff_manifests
from .memory_index import InMemoryIndex
from .port import IndexHit, IndexPort, IndexStatus

__all__ = ["IndexDelta", "IndexManifest", "SourceEntry", "build_manifest", "diff_manifests",
           "IndexHit", "IndexPort", "IndexStatus", "InMemoryIndex"]
