"""Disposable worker tests: no filesystem, network, journal or real Qdrant."""
import pytest

from core.backend.models import Memory
from core.indexing.reconcile_plan import Action
from core.indexing.worker_upsert import apply_upsert

SHA = "a" * 64


class FakeIndex:
    def __init__(self, fail=False):
        self.calls = []
        self.fail = fail

    def revision_for(self, information_id):
        return 2 if information_id in self.calls else None

    def upsert(self, memory):
        self.calls.append(memory.information_id)
        if self.fail:
            raise TimeoutError("ack uncertain")


def operation(**overrides):
    memory = Memory("doc", content="canonical", revision=2)
    args = dict(
        action=Action("INDEX_UPSERT", "doc", 1, 2, "published"),
        read_canonical=lambda _: (memory, SHA),
        authorize=lambda profile, identity, action: True,
        index=FakeIndex(), profile_id="owner", model_id="embedding-v1",
        expected_model_id="embedding-v1", expected_profile_id="owner",
        expected_sha256=SHA,
    )
    args.update(overrides)
    return args


def test_valid_upsert_acknowledged_once():
    args = operation()
    receipt = apply_upsert(**args)
    assert receipt.state == "ACKNOWLEDGED"
    assert args["index"].calls == ["doc"]


@pytest.mark.parametrize("changes", [
    {"authorize": lambda *args: False},
    {"expected_sha256": "b" * 64},
    {"expected_profile_id": "someone-else"},
    {"expected_model_id": "embedding-v2"},
    {"read_canonical": lambda _: (Memory("doc", content="new", revision=3), SHA)},
])
def test_mismatch_refuses_without_effect(changes):
    args = operation(**changes)
    receipt = apply_upsert(**args)
    assert receipt.state == "REFUSED"
    assert args["index"].calls == []


def test_wrong_canonical_identity_never_indexes():
    args = operation(read_canonical=lambda _: (Memory("other", content="wrong"), SHA))
    with pytest.raises(ValueError, match="identity"):
        apply_upsert(**args)
    assert args["index"].calls == []


def test_delete_cannot_be_dispatched():
    args = operation(action=Action("INDEX_DELETE", "doc", 1, 2, "delete"))
    with pytest.raises(ValueError, match="invalid worker"):
        apply_upsert(**args)
    assert args["index"].calls == []


def test_uncertain_ack_is_not_reported_as_success():
    args = operation(index=FakeIndex(fail=True))
    with pytest.raises(TimeoutError):
        apply_upsert(**args)
    assert args["index"].calls == ["doc"]


def test_reader_failure_does_not_touch_index():
    def offline(_):
        raise OSError("canonical unavailable")
    args = operation(read_canonical=offline)
    with pytest.raises(OSError):
        apply_upsert(**args)
    assert args["index"].calls == []


def test_authorization_must_be_boolean():
    args = operation(authorize=lambda *args: "yes")
    with pytest.raises(ValueError, match="authorization"):
        apply_upsert(**args)
    assert args["index"].calls == []


def test_canonical_changes_during_upsert_never_acknowledged():
    index = FakeIndex()
    state = {"revision": 2}
    def reader(_):
        return Memory("doc", revision=state["revision"], content="canonical"), SHA
    def writing(memory):
        index.calls.append(memory.information_id)
        state["revision"] = 3
    index.upsert = writing
    receipt = apply_upsert(**operation(index=index, read_canonical=reader))
    assert receipt.state == "STALE"
    assert index.calls == ["doc"]


def test_permission_revoked_during_upsert_never_acknowledged():
    index = FakeIndex()
    rights = {"allowed": True}
    def writing(memory):
        index.calls.append(memory.information_id)
        rights["allowed"] = False
    index.upsert = writing
    receipt = apply_upsert(**operation(index=index, authorize=lambda *args: rights["allowed"]))
    assert receipt.state == "STALE"
    assert index.calls == ["doc"]


def test_canonical_reader_fails_after_write_no_false_acknowledgement():
    index = FakeIndex()
    reads = {"count": 0}
    def reader(_):
        reads["count"] += 1
        if reads["count"] == 2:
            raise OSError("canonical unavailable after write")
        return Memory("doc", revision=2, content="canonical"), SHA
    with pytest.raises(OSError):
        apply_upsert(**operation(index=index, read_canonical=reader))
    assert index.calls == ["doc"]


def test_adapter_embedding_mismatch_refused_without_effect():
    index = FakeIndex()
    index.embedding_id = "embedding-v2"
    receipt = apply_upsert(**operation(index=index))
    assert receipt.state == "REFUSED"
    assert index.calls == []


def test_matching_adapter_embedding_identity_is_accepted():
    index = FakeIndex()
    index.embedding_id = "embedding-v1"
    receipt = apply_upsert(**operation(index=index))
    assert receipt.state == "ACKNOWLEDGED"
    assert index.calls == ["doc"]
