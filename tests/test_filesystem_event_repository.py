import json

import pytest

from core.events.errors import EventAlreadyExists, InvalidEvent
from core.events.filesystem import FilesystemEventRepository
from core.events.models import (
    Cause,
    CauseType,
    Event,
    EventRelation,
    EventType,
    Provenance,
    RelationType,
    StateTransition,
    Validation,
    ValidationMode,
    ValidationStatus,
)


def test_event_repository_rejects_symlinked_paths(tmp_path):
    external = tmp_path / "external.md"
    external.write_text("private")
    root = tmp_path / "events"
    root.symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(InvalidEvent, match="directory is a symlink"):
        FilesystemEventRepository(root)
    root.unlink()
    repository = FilesystemEventRepository(root)
    (root / "event-test.md").symlink_to(external)
    with pytest.raises(InvalidEvent, match="path is a symlink"):
        repository.get("event-test")
    with pytest.raises(InvalidEvent, match="path is a symlink"):
        repository.list_for_target("info-test")
    with pytest.raises(EventAlreadyExists):
        repository.save(Event("event-test", 1, EventType.CREATED, information_id="info-test"))
    assert external.read_text() == "private"


def test_save_and_get_event(tmp_path):
    repository = FilesystemEventRepository(
        events_root=tmp_path / "events",
    )

    event = Event(
        event_id="event-test-001",
        information_id="info-test-001",
        revision=2,
        event_type=EventType.UPDATED,
        state_transition=StateTransition(
            before={
                "epistemic_status": "UNVERIFIED",
                "operational_state": "ACTIVE",
            },
            after={
                "epistemic_status": "CONFIRMED",
                "operational_state": "ACTIVE",
            },
        ),
        cause=Cause(
            type=CauseType.USER_VALIDATION,
            description="Validation test.",
        ),
        provenance=Provenance(
            source_type="USER_STATEMENT",
            source="test",
            actor="tester",
            timestamp="2026-09-28T00:00:00+02:00",
        ),
        validation=Validation(
            mode=ValidationMode.HUMAN,
            status=ValidationStatus.ACCEPTED,
        ),
        relations=[
            EventRelation(
                type=RelationType.CONCERNS,
                target="info-test-001",
            )
        ],
    )

    saved = repository.save(event)

    assert saved is event

    loaded = repository.get("event-test-001")

    assert loaded is not None
    assert loaded == event


def test_save_rejects_duplicate_event_id(tmp_path):
    repository = FilesystemEventRepository(
        events_root=tmp_path / "events",
    )

    event = Event(
        event_id="event-test-002",
        information_id="info-test-002",
        revision=1,
        event_type=EventType.CREATED,
    )

    repository.save(event)

    with pytest.raises(EventAlreadyExists):
        repository.save(event)


def test_list_for_information_target(tmp_path):
    repository = FilesystemEventRepository(
        events_root=tmp_path / "events",
    )

    repository.save(
        Event(
            event_id="event-test-003",
            information_id="info-target",
            revision=1,
            event_type=EventType.CREATED,
        )
    )

    repository.save(
        Event(
            event_id="event-test-004",
            information_id="info-other",
            revision=1,
            event_type=EventType.CREATED,
        )
    )

    events = repository.list_for_target("info-target")

    assert [event.event_id for event in events] == ["event-test-003"]


def test_list_for_thread_target(tmp_path):
    repository = FilesystemEventRepository(
        events_root=tmp_path / "events",
    )

    repository.save(
        Event(
            event_id="event-test-005",
            thread_id="thread-target",
            revision=2,
            event_type=EventType.STATUS_CHANGED,
            state_transition=StateTransition(
                before={"status": "IMPLEMENTATION"},
                after={"status": "TESTING"},
            ),
        )
    )

    events = repository.list_for_target("thread-target")

    assert [event.event_id for event in events] == ["event-test-005"]


def test_get_returns_none_for_missing_event(tmp_path):
    repository = FilesystemEventRepository(
        events_root=tmp_path / "events",
    )

    assert repository.get("event-missing") is None


def test_rejects_invalid_event_id(tmp_path):
    from core.events.errors import InvalidEvent

    repository = FilesystemEventRepository(
        events_root=tmp_path / "events",
    )

    event = Event(
        event_id="../event-invalid",
        information_id="info-test",
        revision=1,
        event_type=EventType.CREATED,
    )

    with pytest.raises(InvalidEvent):
        repository.save(event)


def test_get_rejects_corrupted_event(tmp_path):
    from core.events.errors import InvalidEvent

    events_root = tmp_path / "events"
    repository = FilesystemEventRepository(
        events_root=events_root,
    )

    corrupted = events_root / "event-corrupted.md"
    corrupted.write_text(
        "# Eidolon Memory Event\n\n"
        "Version: 0.2\n\n"
        "```json\n"
        "{this is not valid json}\n"
        "```\n",
        encoding="utf-8",
    )

    with pytest.raises(InvalidEvent):
        repository.get("event-corrupted")


def test_list_for_target_rejects_corrupted_event(tmp_path):
    from core.events.errors import InvalidEvent

    events_root = tmp_path / "events"
    repository = FilesystemEventRepository(
        events_root=events_root,
    )

    (events_root / "event-corrupted.md").write_text(
        "# Eidolon Memory Event\n\n"
        "Version: 0.2\n\n"
        "```json\n"
        "{this is not valid json}\n"
        "```\n",
        encoding="utf-8",
    )

    with pytest.raises(InvalidEvent):
        repository.list_for_target("info-test")


@pytest.mark.parametrize("corruption", [
    '"event_id": "event-corrupted", "event_id": "other", "revision": 1',
    '"event_id": "event-corrupted", "revision": NaN',
    '"event_id": "event-corrupted", "revision": 1, '
    '"state_transition": {"before": {"other": 1}}',
])
def test_rejects_ambiguous_or_invalid_persisted_event(tmp_path, corruption):
    repository = FilesystemEventRepository(tmp_path / "events")
    (repository.events_root / "event-corrupted.md").write_text(
        "# Eidolon Memory Event\n\nVersion: 0.2\n\n```json\n"
        "{" + corruption + ', "information_id": "info", '
        '"event_type": "UPDATED"}' + "\n```\n",
        encoding="utf-8",
    )

    with pytest.raises(InvalidEvent):
        repository.get("event-corrupted")
    with pytest.raises(InvalidEvent):
        repository.list_for_target("info")


def test_save_rejects_nonfinite_event_data_without_creating_file(tmp_path):
    repository = FilesystemEventRepository(tmp_path / "events")
    event = Event(
        event_id="nonfinite", information_id="info", revision=1,
        event_type=EventType.UPDATED,
        state_transition=StateTransition(after={"epistemic_status": float("nan")}),
    )

    with pytest.raises(InvalidEvent, match="serialized"):
        repository.save(event)
    assert repository.get("nonfinite") is None


@pytest.mark.parametrize("overrides", [
    {"revision": "2"},
    {"revision": True},
    {"information_id": 42},
    {"state_transition": {"before": [], "after": {}}},
    {"relations": ["not an object"]},
])
def test_read_rejects_wrong_event_field_types(tmp_path, overrides):
    repository = FilesystemEventRepository(tmp_path / "events")
    payload = {"event_id": "bad-types", "information_id": "info", "revision": 2,
               "event_type": "UPDATED"}
    payload.update(overrides)
    (repository.events_root / "bad-types.md").write_text(
        "# Eidolon Memory Event\n\nVersion: 0.2\n\n```json\n"
        + json.dumps(payload) + "\n```\n", encoding="utf-8",
    )
    with pytest.raises(InvalidEvent):
        repository.get("bad-types")


def test_save_rejects_mutated_boolean_revision(tmp_path):
    repository = FilesystemEventRepository(tmp_path / "events")
    event = Event("bad-revision", 1, EventType.CREATED, information_id="info")
    event.revision = True
    with pytest.raises(InvalidEvent, match="revision"):
        repository.save(event)
