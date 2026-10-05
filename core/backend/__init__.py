# ==========================================================
# Projet      : Eidolon Memory Engine
# Organisation: Eidolon Core Technologies (ECT)
# Fichier     : core/backend/__init__.py
# Description : Memory Backend abstraction.
# Standard    : Eidolon Presentation Standard v1
# ==========================================================

"""Memory Backend abstraction."""

from .errors import (
    BackendError,
    BackendUnavailable,
    InvalidMemory,
    MemoryAlreadyExists,
    MemoryNotFound,
    RevisionConflict,
)
from .models import (
    DeleteResult,
    Memory,
    SearchResult,
    StoreResult,
    UpdateResult,
)
from .interface import MemoryBackend
from .filesystem import FilesystemBackend

__all__ = [
    "Memory",
    "StoreResult",
    "UpdateResult",
    "DeleteResult",
    "SearchResult",
    "MemoryBackend",
    "FilesystemBackend",
    "BackendError",
    "BackendUnavailable",
    "InvalidMemory",
    "MemoryAlreadyExists",
    "MemoryNotFound",
    "RevisionConflict",
]
