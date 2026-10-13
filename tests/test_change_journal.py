"""Isolated SQLite journal tests; no Qdrant, canonical mutation or VM."""
import hashlib
import pytest

from core.indexing.change_journal import ChangeJournal


def test_intent_survives_reopen_and_replay(tmp_path):
    path = tmp_path / "changes.sqlite3"
    journal = ChangeJournal(path)
    digest = hashlib.sha256(b"canonical").hexdigest()
    seq = journal.begin("conversation-1", 2, "UPSERT", digest)
    assert journal.pending()[0].state == "INTENT"
    reopened = ChangeJournal(path)
    assert reopened.pending()[0].sequence == seq
    reopened.published(seq)
    reopened.published(seq)
    assert reopened.pending()[0].state == "PUBLISHED"
    reopened.indexed(seq)
    reopened.indexed(seq)
    assert reopened.pending() == ()


def test_interrupted_intent_remains_visible(tmp_path):
    journal = ChangeJournal(tmp_path / "changes.sqlite3")
    journal.begin("archive-1", 1, "DELETE")
    # A crash before canonical rename must not make an intent disappear.
    assert [(x.operation, x.state) for x in ChangeJournal(journal.path).pending()] == [("DELETE", "INTENT")]


def test_transition_cannot_skip_canonical_ack(tmp_path):
    journal = ChangeJournal(tmp_path / "changes.sqlite3")
    seq = journal.begin("archive-1", 1, "DELETE")
    with pytest.raises(ValueError, match="transition"):
        journal.indexed(seq)
    journal.published(seq)
    with pytest.raises(ValueError, match="unknown intent"):
        journal.published(seq + 1)


@pytest.mark.parametrize("args", [
    ("../secret", 1, "DELETE", None),
    ("archive", 0, "DELETE", None),
    ("archive", True, "DELETE", None),
    ("archive", 1, "UPSERT", None),
    ("archive", 1, "UPSERT", "invalid"),
    ("archive", 1, "DELETE", "a" * 64),
    ("archive", 1, "UNKNOWN", None),
])
def test_invalid_intents_are_rejected(tmp_path, args):
    journal = ChangeJournal(tmp_path / "changes.sqlite3")
    with pytest.raises(ValueError):
        journal.begin(*args)


def test_pending_order_and_limit(tmp_path):
    journal = ChangeJournal(tmp_path / "changes.sqlite3")
    first = journal.begin("a", 1, "DELETE")
    second = journal.begin("b", 2, "DELETE")
    assert [x.sequence for x in journal.pending(limit=1)] == [first]
    journal.published(first)
    journal.indexed(first)
    assert [x.sequence for x in journal.pending()] == [second]
    with pytest.raises(ValueError):
        journal.pending(limit=0)
