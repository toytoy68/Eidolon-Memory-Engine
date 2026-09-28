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


def test_information_event_model():
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
            description="Validation par l'utilisateur.",
        ),
        provenance=Provenance(
            source_type="USER_STATEMENT",
            source="chat",
            actor="user",
            timestamp="2026-09-27T00:00:00+02:00",
        ),
        validation=Validation(
            mode=ValidationMode.HUMAN,
            status=ValidationStatus.ACCEPTED,
        ),
    )

    assert event.information_id == "info-test-001"
    assert event.thread_id is None
    assert event.revision == 2
    assert event.event_type is EventType.UPDATED
    assert event.state_transition.after["epistemic_status"] == "CONFIRMED"


def test_thread_status_changed_event_model():
    event = Event(
        event_id="event-test-002",
        thread_id="thread-test-001",
        revision=4,
        event_type=EventType.STATUS_CHANGED,
        state_transition=StateTransition(
            before={"status": "IMPLEMENTATION"},
            after={"status": "TESTING"},
        ),
        cause=Cause(
            type=CauseType.MANUAL_ACTION,
            description="Passage en phase de test.",
        ),
    )

    assert event.thread_id == "thread-test-001"
    assert event.information_id is None
    assert event.revision == 4
    assert event.event_type is EventType.STATUS_CHANGED
    assert event.state_transition.before["status"] == "IMPLEMENTATION"
    assert event.state_transition.after["status"] == "TESTING"


def test_event_supports_relations():
    event = Event(
        event_id="event-test-003",
        information_id="info-test-003",
        revision=1,
        event_type=EventType.CREATED,
        relations=[
            EventRelation(
                type=RelationType.CONCERNS,
                target="project-test",
            )
        ],
    )

    assert len(event.relations) == 1
    assert event.relations[0].type is RelationType.CONCERNS
    assert event.relations[0].target == "project-test"


def test_event_defaults_are_independent():
    first = Event(
        event_id="event-test-004",
        information_id="info-test-004",
        revision=1,
        event_type=EventType.CREATED,
    )
    second = Event(
        event_id="event-test-005",
        information_id="info-test-005",
        revision=1,
        event_type=EventType.CREATED,
    )

    first.evidence.supporting.append("evidence-1")

    assert first.evidence.supporting == ["evidence-1"]
    assert second.evidence.supporting == []


def test_event_requires_exactly_one_target():
    import pytest

    with pytest.raises(ValueError, match="exactement une Information ou un Thread"):
        Event(
            event_id="event-test-005",
            revision=1,
            event_type=EventType.CREATED,
        )

    with pytest.raises(ValueError, match="exactement une Information ou un Thread"):
        Event(
            event_id="event-test-006",
            information_id="info-test-006",
            thread_id="thread-test-006",
            revision=1,
            event_type=EventType.CREATED,
        )


def test_event_requires_positive_revision():
    import pytest

    with pytest.raises(ValueError, match="revision doit être >= 1"):
        Event(
            event_id="event-test-007",
            information_id="info-test-007",
            revision=0,
            event_type=EventType.CREATED,
        )


def test_status_changed_is_reserved_for_threads():
    import pytest

    with pytest.raises(ValueError, match="STATUS_CHANGED est réservé"):
        Event(
            event_id="event-test-008",
            information_id="info-test-008",
            revision=1,
            event_type=EventType.STATUS_CHANGED,
        )


def test_non_status_event_is_reserved_for_information():
    import pytest

    with pytest.raises(ValueError, match="Events d Information"):
        Event(
            event_id="event-test-009",
            thread_id="thread-test-009",
            revision=1,
            event_type=EventType.UPDATED,
        )


def test_information_event_validator_accepts_valid_transition():
    from core.events.validator import is_valid

    event = Event(
        event_id="event-validator-001",
        information_id="info-validator-001",
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
    )

    assert is_valid(event)


def test_thread_status_changed_requires_status():
    from core.events.validator import validate_event

    event = Event(
        event_id="event-validator-002",
        thread_id="thread-validator-001",
        revision=2,
        event_type=EventType.STATUS_CHANGED,
        state_transition=StateTransition(
            before={"status": "IMPLEMENTATION"},
            after={},
        ),
    )

    errors = validate_event(event)

    assert "STATUS_CHANGED nécessite status dans state_transition.after" in errors


def test_information_event_requires_information_state_when_transition_present():
    from core.events.validator import validate_event

    event = Event(
        event_id="event-validator-003",
        information_id="info-validator-002",
        revision=2,
        event_type=EventType.UPDATED,
        state_transition=StateTransition(
            before={"status": "ACTIVE"},
            after={"status": "COMPLETED"},
        ),
    )

    errors = validate_event(event)

    assert (
        "state_transition.before doit contenir un état Information"
        in errors
    )
    assert (
        "state_transition.after doit contenir un état Information"
        in errors
    )


def test_validator_accepts_information_event_without_transition():
    from core.events.validator import is_valid

    event = Event(
        event_id="event-validator-004",
        information_id="info-validator-003",
        revision=1,
        event_type=EventType.CREATED,
    )

    assert is_valid(event)


def test_thread_created_event_requires_initial_status_and_revision():
    from core.events.validator import is_valid, validate_event

    event = Event(
        event_id="thread-created", thread_id="thread-1", revision=1,
        event_type=EventType.CREATED,
        state_transition=StateTransition(after={"status": "PROPOSED"}),
    )
    assert is_valid(event)
    assert "CREATED Thread nécessite revision 1" in validate_event(
        Event("bad-created", 2, EventType.CREATED, thread_id="thread-1",
              state_transition=StateTransition(after={"status": "PROPOSED"})))
    assert "CREATED Thread nécessite status dans state_transition.after" in validate_event(
        Event("bad-status", 1, EventType.CREATED, thread_id="thread-1"))
