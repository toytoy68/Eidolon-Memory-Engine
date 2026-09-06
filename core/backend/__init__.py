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

__all__ = [
    "Memory",
    "StoreResult",
    "UpdateResult",
    "DeleteResult",
    "SearchResult",
    "MemoryBackend",
    "BackendError",
    "BackendUnavailable",
    "InvalidMemory",
    "MemoryAlreadyExists",
    "MemoryNotFound",
    "RevisionConflict",
]
