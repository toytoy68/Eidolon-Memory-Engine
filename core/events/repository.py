# ==========================================================
# Projet      : Eidolon Memory Engine
# Organisation: Eidolon Core Technologies (ECT)
# Fichier     : core/events/repository.py
# Description : Repository contract for Eidolon Memory Events.
# Standard    : Eidolon Presentation Standard v1
# ==========================================================

"""Repository contract for Eidolon Memory Events."""

from __future__ import annotations

from abc import ABC, abstractmethod

from .models import Event


class EventRepository(ABC):
    """Persistence contract for append-only Memory Events."""

    @abstractmethod
    def save(self, event: Event) -> Event:
        """Persist an Event."""

    @abstractmethod
    def get(self, event_id: str) -> Event | None:
        """Return an Event by identifier."""

    @abstractmethod
    def list_for_target(self, target_id: str) -> list[Event]:
        """Return Events associated with an Information or Thread."""
