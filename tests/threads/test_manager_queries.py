from core.threads.models import (
    ActionStatus,
    Thread,
    ThreadAction,
    ThreadStatus,
)

from core.threads.queries import (
    ThreadQuery,
    ThreadQueryType,
    ThreadSortField,
    ThreadSortOrder,
)

from core.threads.storage import ThreadStorage

from core.threads.manager import ThreadManager


def make_thread(
    thread_id: str,
    title: str,
    status: ThreadStatus,
    updated_at: str,
    actions: list[ThreadAction] | None = None,
) -> Thread:
    return Thread(
        thread_id=thread_id,
        title=title,
        objective=f"Objective {thread_id}",
        status=status,
        revision=1,
        actions=actions or [],
        created_at="2026-09-01T10:00:00+02:00",
        updated_at=updated_at,
    )


def test_list_threads_returns_all_threads():
    threads = [
        make_thread(
            "thread-1",
            "Alpha",
            ThreadStatus.IMPLEMENTATION,
            "2026-09-10T10:00:00+02:00",
        ),
        make_thread(
            "thread-2",
            "Beta",
            ThreadStatus.TESTING,
            "2026-09-11T10:00:00+02:00",
        ),
    ]

    query = ThreadQuery(
        query_type=ThreadQueryType.LIST_THREADS,
    )

    result = ThreadManager.query(threads, query)

    assert [thread.thread_id for thread in result] == [
        "thread-2",
        "thread-1",
    ]


def test_list_open_threads_excludes_completed_and_cancelled():
    threads = [
        make_thread(
            "open",
            "Open",
            ThreadStatus.IMPLEMENTATION,
            "2026-09-10T10:00:00+02:00",
        ),
        make_thread(
            "completed",
            "Completed",
            ThreadStatus.COMPLETED,
            "2026-09-11T10:00:00+02:00",
        ),
        make_thread(
            "cancelled",
            "Cancelled",
            ThreadStatus.CANCELLED,
            "2026-09-12T10:00:00+02:00",
        ),
    ]

    completed = threads[1]
    completed.completed_at = "2026-09-11T12:00:00+02:00"

    query = ThreadQuery(
        query_type=ThreadQueryType.LIST_OPEN_THREADS,
    )

    result = ThreadManager.query(threads, query)

    assert [thread.thread_id for thread in result] == ["open"]


def test_list_threads_by_status():
    threads = [
        make_thread(
            "impl",
            "Implementation",
            ThreadStatus.IMPLEMENTATION,
            "2026-09-10T10:00:00+02:00",
        ),
        make_thread(
            "testing",
            "Testing",
            ThreadStatus.TESTING,
            "2026-09-11T10:00:00+02:00",
        ),
    ]

    query = ThreadQuery(
        query_type=ThreadQueryType.LIST_THREADS_BY_STATUS,
        status=ThreadStatus.TESTING,
    )

    result = ThreadManager.query(threads, query)

    assert [thread.thread_id for thread in result] == ["testing"]


def test_get_thread():
    threads = [
        make_thread(
            "thread-1",
            "Alpha",
            ThreadStatus.IMPLEMENTATION,
            "2026-09-10T10:00:00+02:00",
        ),
        make_thread(
            "thread-2",
            "Beta",
            ThreadStatus.TESTING,
            "2026-09-11T10:00:00+02:00",
        ),
    ]

    query = ThreadQuery(
        query_type=ThreadQueryType.GET_THREAD,
        thread_id="thread-2",
    )

    result = ThreadManager.query(threads, query)

    assert len(result) == 1
    assert result[0].thread_id == "thread-2"


def test_filter_by_title_contains():
    threads = [
        make_thread(
            "thread-1",
            "Watercooling V100",
            ThreadStatus.IMPLEMENTATION,
            "2026-09-10T10:00:00+02:00",
        ),
        make_thread(
            "thread-2",
            "Memory Engine",
            ThreadStatus.TESTING,
            "2026-09-11T10:00:00+02:00",
        ),
    ]

    query = ThreadQuery(
        query_type=ThreadQueryType.LIST_THREADS,
        title_contains="v100",
    )

    result = ThreadManager.query(threads, query)

    assert [thread.thread_id for thread in result] == ["thread-1"]


def test_sort_ascending():
    threads = [
        make_thread(
            "new",
            "New",
            ThreadStatus.TESTING,
            "2026-09-12T10:00:00+02:00",
        ),
        make_thread(
            "old",
            "Old",
            ThreadStatus.IMPLEMENTATION,
            "2026-09-10T10:00:00+02:00",
        ),
    ]

    query = ThreadQuery(
        query_type=ThreadQueryType.LIST_THREADS,
        sort_by=ThreadSortField.UPDATED_AT,
        sort_order=ThreadSortOrder.ASC,
    )

    result = ThreadManager.query(threads, query)

    assert [thread.thread_id for thread in result] == [
        "old",
        "new",
    ]


def test_pagination():
    threads = [
        make_thread(
            f"thread-{index}",
            f"Thread {index}",
            ThreadStatus.IMPLEMENTATION,
            f"2026-09-{10 + index:02d}T10:00:00+02:00",
        )
        for index in range(3)
    ]

    query = ThreadQuery(
        query_type=ThreadQueryType.LIST_THREADS,
        limit=1,
        offset=1,
    )

    result = ThreadManager.query(threads, query)

    assert len(result) == 1
    assert result[0].thread_id == "thread-1"


def test_list_open_actions():
    threads = [
        make_thread(
            "thread-1",
            "Alpha",
            ThreadStatus.IMPLEMENTATION,
            "2026-09-10T10:00:00+02:00",
            actions=[
                ThreadAction(
                    "a1",
                    "Action one",
                    ActionStatus.IN_PROGRESS,
                ),
                ThreadAction(
                    "a2",
                    "Action two",
                    ActionStatus.COMPLETED,
                ),
            ],
        ),
    ]

    query = ThreadQuery(
        query_type=ThreadQueryType.LIST_OPEN_ACTIONS,
    )

    result = ThreadManager.query(threads, query)

    assert len(result) == 1
    assert result[0][1].action_id == "a1"

def test_query_persisted_threads(tmp_path):
    storage = ThreadStorage(tmp_path)

    thread = Thread(
        thread_id="thread-persisted-001",
        title="Persistent Thread",
        objective="Test persisted query",
        status=ThreadStatus.IMPLEMENTATION,
        revision=1,
        created_at="2026-09-20T10:00:00+02:00",
        updated_at="2026-09-20T11:00:00+02:00",
    )

    storage.create(thread)

    loaded_threads = storage.list()

    query = ThreadQuery(
        query_type=ThreadQueryType.LIST_OPEN_THREADS,
    )

    result = ThreadManager.query(
        loaded_threads,
        query,
    )

    assert len(result) == 1
    assert result[0].thread_id == "thread-persisted-001"
