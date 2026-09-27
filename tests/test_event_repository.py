import pytest

from core.events.models import Event
from core.events.repository import EventRepository


def test_event_repository_is_abstract():
    with pytest.raises(TypeError):
        EventRepository()


def test_event_repository_requires_all_methods():
    class IncompleteRepository(EventRepository):
        def save(self, event: Event) -> Event:
            return event

        def get(self, event_id: str) -> Event | None:
            return None

    with pytest.raises(TypeError):
        IncompleteRepository()


def test_event_repository_can_be_implemented():
    class CompleteRepository(EventRepository):
        def save(self, event: Event) -> Event:
            return event

        def get(self, event_id: str) -> Event | None:
            return None

        def list_for_target(self, target_id: str) -> list[Event]:
            return []

    repository = CompleteRepository()

    assert isinstance(repository, EventRepository)
