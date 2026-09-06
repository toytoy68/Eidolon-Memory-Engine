"""Errors raised by MemoryBackend implementations."""


class BackendError(Exception):
    """Base exception for backend failures."""


class BackendUnavailable(BackendError):
    """Backend cannot currently be reached or used."""


class InvalidMemory(BackendError):
    """Memory object is invalid for persistence."""


class MemoryAlreadyExists(BackendError):
    """A memory with the requested identifier already exists."""


class MemoryNotFound(BackendError):
    """Requested memory does not exist."""


class RevisionConflict(BackendError):
    """Update was based on an outdated revision."""
