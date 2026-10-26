"""Laboratory verification of opt-in owner-bound access and same-ID locking."""
from concurrent.futures import ThreadPoolExecutor

import pytest

from core.backend.authorized_memory_experimental import AuthorizedMemory, Principal
from core.backend.errors import MemoryNotFound, RevisionConflict
from core.backend.fts5_backend import FTS5Backend
from core.backend.models import Memory


def backend(tmp_path):
    return FTS5Backend(
        persistent_root=tmp_path / "canonical",
        history_root=tmp_path / "history",
    )


def test_cross_owner_reads_search_list_and_updates_denied(tmp_path):
    b = backend(tmp_path)
    alice = AuthorizedMemory(b, Principal("alice"))
    bob = AuthorizedMemory(b, Principal("bob"))
    alice.store(Memory(information_id="a", content="secret alice", metadata={"owner": "alice"}))
    bob.store(Memory(information_id="b", content="secret bob", metadata={"owner": "bob"}))
    assert [r.memory.information_id for r in alice.search("secret")] == ["a"]
    assert [m.information_id for m in bob.list()] == ["b"]
    with pytest.raises(MemoryNotFound):
        alice.get("b")
    with pytest.raises(MemoryNotFound):
        alice.update(
            "b", Memory(information_id="b", content="wrong", metadata={"owner": "alice"}), 1
        )
    with pytest.raises(MemoryNotFound):
        alice.delete_request("b", "alice", "attempt", 1, "op")


def test_missing_owner_and_anonymous_are_denied(tmp_path):
    b = backend(tmp_path)
    b.store(Memory(information_id="legacy", content="private legacy"))
    alice = AuthorizedMemory(b, Principal("alice"))
    assert alice.search("private") == []
    with pytest.raises(MemoryNotFound):
        alice.get("legacy")
    with pytest.raises(PermissionError):
        Principal("")


def test_same_revision_cannot_be_accepted_twice(tmp_path):
    b = backend(tmp_path)
    b.store(Memory(information_id="one", content="initial"))

    def compete(i):
        try:
            b.update("one", Memory(information_id="one", content=str(i)), 1)
            return "updated"
        except RevisionConflict:
            return "conflict"

    with ThreadPoolExecutor(max_workers=12) as executor:
        outcomes = list(executor.map(compete, range(30)))

    assert outcomes.count("updated") == 1
    assert outcomes.count("conflict") == 29
    assert b.get("one").revision == 2


def test_raw_backend_bypasses_facade_known_risk(tmp_path):
    b = backend(tmp_path)
    b.store(Memory(information_id="b", content="bob confidential", metadata={"owner": "bob"}))
    assert AuthorizedMemory(b, Principal("alice")).search("confidential") == []
    # Documents why this facade is not a production authentication boundary:
    assert b.search("confidential")
