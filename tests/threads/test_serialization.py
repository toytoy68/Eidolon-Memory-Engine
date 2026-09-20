from core.threads.models import ActionStatus, Thread, ThreadAction, ThreadStatus
from core.threads.serialization import thread_to_dict


def make_thread() -> Thread:
    return Thread(
        thread_id="thread-serialization-001",
        title="Serialization Thread",
        objective="Test Thread serialization",
        status=ThreadStatus.IMPLEMENTATION,
        revision=3,
        context={"source": "test"},
        actions=[
            ThreadAction(
                action_id="action-001",
                description="Test action",
                status=ActionStatus.IN_PROGRESS,
                metadata={"priority": "high"},
            )
        ],
        relations=[
            {"type": "RELATED_TO", "target": "thread-002"},
        ],
        created_at="2026-09-20T10:00:00+02:00",
        updated_at="2026-09-20T11:00:00+02:00",
        started_at="2026-09-20T10:30:00+02:00",
        provenance={"source": "unit-test"},
    )


def test_thread_to_dict():
    result = thread_to_dict(make_thread())

    assert result["thread_id"] == "thread-serialization-001"
    assert result["title"] == "Serialization Thread"
    assert result["objective"] == "Test Thread serialization"
    assert result["status"] == "IMPLEMENTATION"
    assert result["revision"] == 3
    assert result["context"] == {"source": "test"}
    assert result["created_at"] == "2026-09-20T10:00:00+02:00"
    assert result["started_at"] == "2026-09-20T10:30:00+02:00"


def test_thread_to_dict_serializes_actions():
    result = thread_to_dict(make_thread())

    assert result["actions"] == [
        {
            "action_id": "action-001",
            "description": "Test action",
            "status": "IN_PROGRESS",
            "metadata": {"priority": "high"},
        }
    ]


def test_thread_to_dict_preserves_relations_and_provenance():
    result = thread_to_dict(make_thread())

    assert result["relations"] == [
        {"type": "RELATED_TO", "target": "thread-002"},
    ]
    assert result["provenance"] == {"source": "unit-test"}
