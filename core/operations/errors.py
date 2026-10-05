# ==========================================================
# Projet      : Eidolon Memory Engine
# Organisation: Eidolon Core Technologies (ECT)
# Fichier     : core/operations/errors.py
# Description : Exceptions for persistent Operations.
# Standard    : Eidolon Presentation Standard v1
# ==========================================================

"""Exceptions for persistent Operations."""


class OperationRepositoryError(Exception):
    """Base exception for Operation repository failures."""


class OperationAlreadyExists(OperationRepositoryError):
    """Raised when creating an Operation that already exists."""


class OperationNotFound(OperationRepositoryError):
    """Raised when updating an Operation that does not exist."""


class InvalidOperationRecord(OperationRepositoryError):
    """Raised when a persisted Operation record is invalid or corrupted."""


class OperationConflict(OperationRepositoryError):
    """Raised when an update conflicts with the persisted Operation."""
