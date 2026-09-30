"""Abrupt process exits at each persisted Information deletion boundary."""

import json
import multiprocessing
import os
from pathlib import Path

import pytest

from core.backend.filesystem import FilesystemBackend
from core.backend.models import Memory
from core.information.deletion_recovery import recover_deletions


def crash_deletion_worker(root: str, phase: str) -> None:
    base = Path(root)
    backend = FilesystemBackend(base / "memory/persistent", base / "memory/history")
    backend.store(Memory("info-1", content="kept until deletion"))
    receipt = backend.pending_delete_root / "info-1.json"
    document = backend._path("info-1")
    original_write = backend._atomic_write

    def exit_after_receipt(path, content):
        original_write(path, content)
        if path == receipt and json.loads(content)["status"] == {
                "requested": "PENDING_DELETE", "applying": "APPLYING_DELETE",
                "committed": "DELETED"}.get(phase):
            os._exit(74)

    backend._atomic_write = exit_after_receipt
    if phase == "removed":
        original_unlink = Path.unlink

        def exit_after_unlink(path, *args, **kwargs):
            original_unlink(path, *args, **kwargs)
            if path == document:
                os._exit(74)

        Path.unlink = exit_after_unlink
    backend.delete_request("info-1", "human", "obsolete", 1, "delete-1")
    backend.approve_delete("info-1", "delete-1")
    os._exit(75)  # A hook must have stopped the worker.


@pytest.mark.parametrize("phase", ["requested", "applying", "removed", "committed"])
def test_hard_exit_during_information_deletion_is_reviewable_or_recoverable(tmp_path, phase):
    process = multiprocessing.get_context("spawn").Process(
        target=crash_deletion_worker, args=(str(tmp_path), phase))
    process.start()
    process.join(timeout=20)
    if process.is_alive():
        process.terminate()
        process.join()
        pytest.fail("deletion deadlocked")
    assert process.exitcode == 74

    backend = FilesystemBackend(tmp_path / "memory/persistent", tmp_path / "memory/history")
    receipt = backend.pending_delete_root / "info-1.json"
    expected_status = {"requested": "PENDING_DELETE", "applying": "APPLYING_DELETE",
                       "removed": "APPLYING_DELETE", "committed": "DELETED"}[phase]
    assert json.loads(receipt.read_text())["status"] == expected_status
    assert (backend.get("info-1") is not None) == (phase in {"requested", "applying"})
    if phase == "requested":
        assert recover_deletions(tmp_path) == {"recovered": [], "blocked": []}
        assert backend.approve_delete("info-1", "delete-1").status == "DELETED"
    elif phase == "committed":
        assert recover_deletions(tmp_path) == {"recovered": [], "blocked": []}
    else:
        assert recover_deletions(tmp_path) == {
            "recovered": ["memory/history/pending-delete/info-1.json"], "blocked": []}
    assert backend.get("info-1") is None
    assert json.loads(receipt.read_text())["status"] == "DELETED"
    assert recover_deletions(tmp_path) == {"recovered": [], "blocked": []}
