"""Errors raised by EventRepository implementations."""


class EventRepositoryError(Exception):
    """Base exception for Event repository failures."""


class InvalidEvent(EventRepositoryError):
    """Event is invalid for persistence."""


class EventAlreadyExists(EventRepositoryError):
    """An Event with the requested identifier already exists."""
