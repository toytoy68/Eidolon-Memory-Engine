"""No external Qdrant or canonical corpus is used by these worker tests."""
from core.backend.models import Memory
from core.indexing.reconcile_plan import Action
from tests.experimental_isolated_upsert import run_isolated_upsert

SHA = "a" * 64


class FakeIndex:
    def __init__(self, fail=False):
        self.items = []
        self.fail = fail
    def upsert(self, memory):
        self.items.append(memory)
        if self.fail:
            raise TimeoutError("lost acknowledgment")


def action(kind="INDEX_UPSERT"):
    return Action(kind, "doc", 1 if kind == "INDEX_UPSERT" else None, 2, "test")


def execute(index, reader, policy, **changes):
    options = dict(index=index, read_canonical=reader, authorize=policy,
                   profile_id="owner", model_id="embedding-v1",
                   expected_profile_id="owner", expected_model_id="embedding-v1",
                   expected_sha256=SHA, disposable_test=True)
    options.update(changes)
    return run_isolated_upsert(action(), **options)


def reader(_):
    return Memory("doc", revision=2, content="synthetic"), SHA


def test_valid_upsert_is_not_claimed_confirmed():
    index = FakeIndex()
    result = execute(index, reader, lambda p, d: True)
    assert result.state == "APPLIED_UNCONFIRMED"
    assert len(index.items) == 1


def test_denied_profile_never_writes():
    index = FakeIndex()
    assert execute(index, reader, lambda p, d: False).state == "BLOCKED"
    assert not index.items


def test_changed_canonical_before_effect_blocks():
    index = FakeIndex()
    count = [0]
    def changing(_):
        count[0] += 1
        return Memory("doc", revision=2, content="synthetic"), SHA if count[0] == 1 else "b" * 64
    assert execute(index, changing, lambda p, d: True).state == "BLOCKED"
    assert not index.items


def test_permission_revoked_before_effect_blocks():
    index = FakeIndex()
    checks = [True, False]
    assert execute(index, reader, lambda p, d: checks.pop(0)).state == "BLOCKED"
    assert not index.items


def test_ambiguous_ack_never_claims_success():
    index = FakeIndex(fail=True)
    assert execute(index, reader, lambda p, d: True).state == "UNCERTAIN"


def test_delete_is_rejected():
    index = FakeIndex()
    import pytest
    with pytest.raises(ValueError):
        run_isolated_upsert(action("ENQUEUE_DELETE"), index=index,
                            read_canonical=reader, authorize=lambda p, d: True,
                            profile_id="owner", model_id="embedding-v1",
                            expected_profile_id="owner", expected_model_id="embedding-v1",
                            expected_sha256=SHA, disposable_test=True)
    assert not index.items


def test_embedding_mismatch_blocks():
    index = FakeIndex()
    assert execute(index, reader, lambda p, d: True,
                   expected_model_id="embedding-v2").state == "BLOCKED"
    assert not index.items

def test_disposable_mode_is_required():
    import pytest
    index = FakeIndex()
    with pytest.raises(ValueError, match="disposable"):
        execute(index, reader, lambda p, d: True, disposable_test=False)
    assert not index.items
