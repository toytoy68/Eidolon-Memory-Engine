import json

from core.events.filesystem import FilesystemEventRepository
from core.monitoring.overview import main, overview
from core.operations.filesystem import FilesystemOperationRepository
from core.operations.thread_status import FilesystemThreadOperations
from core.threads.models import Thread, ThreadStatus
from core.threads.storage import ThreadStorage


def test_overview_reads_real_thread_and_operation_without_changing_them(tmp_path, capsys):
    data = tmp_path / "memory"
    storage = ThreadStorage(data / "persistent")
    events = FilesystemEventRepository(data / "history/events/thread-status-v1")
    operations = FilesystemOperationRepository(data / "history/operations/thread-status-v1")
    engine = FilesystemThreadOperations(storage, events, operations)
    storage.create(Thread("t", "Title", "Objective", created_at="2026-01-01",
                          updated_at="2026-01-01"))
    engine.change_status("t", ThreadStatus.VALIDATED, previous_revision=1,
                         operation_id="op", event_id="e")
    before = (operations.root / "op.json").read_bytes()

    assert main(["--root", str(tmp_path)]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report == {
        "threads": {"statuses": {"VALIDATED": 1}, "needs_review": []},
        "thread_status_operations": {
            "statuses": {"COMMITTED": 1}, "needs_review": [],
        },
        "pending_operations": 0,
    }
    assert (operations.root / "op.json").read_bytes() == before


def test_overview_flags_legacy_and_damaged_files(tmp_path):
    threads = tmp_path / "memory/persistent/threads"
    threads.mkdir(parents=True)
    (threads / "old.md").write_text("# Eidolon Thread Object\n\nVersion: 0.1\n")
    ops = tmp_path / "memory/history/operations/thread-status-v1"
    ops.mkdir(parents=True)
    (ops / "broken.json").write_text("{broken")

    report = overview(tmp_path)
    assert report["threads"]["needs_review"] == ["memory/persistent/threads/old.md"]
    assert report["thread_status_operations"]["needs_review"] == [
        "memory/history/operations/thread-status-v1/broken.json",
    ]
    assert report["pending_operations"] == 0
