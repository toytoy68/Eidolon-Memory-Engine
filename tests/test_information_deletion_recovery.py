import hashlib
import json

from core.backend.filesystem import FilesystemBackend
from core.backend.models import Memory
from core.information.deletion_recovery import main, recover_deletions
from core.threads.models import Thread
from core.threads.storage import ThreadStorage


def applying(root, information_id, *, removed=False):
    backend = FilesystemBackend(root / "memory/persistent", root / "memory/history")
    backend.store(Memory(information_id, content="private content"))
    backend.delete_request(information_id, "human", "reason", 1, f"delete-{information_id}")
    document = backend._path(information_id)
    receipt = backend.pending_delete_root / f"{information_id}.json"
    record = json.loads(receipt.read_text())
    record["status"] = "APPLYING_DELETE"
    record["content_sha256"] = hashlib.sha256(document.read_bytes()).hexdigest()
    receipt.write_text(json.dumps(record))
    if removed:
        document.unlink()
    return backend, document, receipt


def test_deletion_recovery_is_opt_in_and_idempotent(tmp_path, capsys):
    backend, document, receipt = applying(tmp_path, "info-1", removed=True)
    before = receipt.read_bytes()
    assert main(["--root", str(tmp_path)]) == 1
    assert "deletion_requires_resume" in capsys.readouterr().out
    assert receipt.read_bytes() == before

    assert main(["--root", str(tmp_path), "--apply"]) == 0
    output = json.loads(capsys.readouterr().out)
    assert output == {"recovered": ["memory/history/pending-delete/info-1.json"], "blocked": []}
    assert not document.exists()
    assert json.loads(receipt.read_text())["status"] == "DELETED"
    assert recover_deletions(tmp_path) == {"recovered": [], "blocked": []}
    assert "private content" not in json.dumps(output)


def test_deletion_recovery_blocks_changed_file_and_linked_thread(tmp_path):
    backend, document, receipt = applying(tmp_path, "changed")
    document.write_text("different content")
    other, linked, linked_receipt = applying(tmp_path, "linked")
    storage = ThreadStorage(other.persistent_root)
    storage.create(Thread("thread-1", "Title", "Objective",
                          relations=[{"type": "CONCERNS", "target_id": "linked"}]))
    report = recover_deletions(tmp_path)
    assert report == {"recovered": [], "blocked": [
        {"path": "memory/history/pending-delete/changed.json", "reason": "RevisionConflict"},
        {"path": "memory/history/pending-delete/linked.json", "reason": "InformationDeletionBlocked"},
    ]}
    assert document.read_text() == "different content"
    assert linked.exists()
    assert json.loads(receipt.read_text())["status"] == "APPLYING_DELETE"
    assert json.loads(linked_receipt.read_text())["status"] == "APPLYING_DELETE"


def test_deletion_recovery_never_infers_old_pending_request(tmp_path):
    backend = FilesystemBackend(tmp_path / "memory/persistent", tmp_path / "memory/history")
    backend.store(Memory("old"))
    backend.delete_request("old", "human", "reason", 1, "delete-old")
    receipt = backend.pending_delete_root / "old.json"
    backend._path("old").unlink()
    before = receipt.read_bytes()
    assert recover_deletions(tmp_path) == {"recovered": [], "blocked": []}
    assert receipt.read_bytes() == before
