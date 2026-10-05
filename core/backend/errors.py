# ==========================================================
# Projet      : Eidolon Memory Engine
# Organisation: Eidolon Core Technologies (ECT)
# Fichier     : core/backend/errors.py
# Description : Errors raised by MemoryBackend implementations.
# Standard    : Eidolon Presentation Standard v1
# ==========================================================

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


class InformationDeletionBlocked(BackendError):
    """A linked or unreadable object prevents safe Information deletion."""
