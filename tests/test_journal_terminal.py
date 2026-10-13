"""Tests for explicit v2 terminal closure and journal age."""
import hashlib
import pytest
from core.indexing.change_journal import ChangeJournal
from core.indexing.journal_migration import migrate_v2
from tests.legacy_journal_fixture import legacy_v1


def test_pending_exposes_creation_time(tmp_path):
    journal = ChangeJournal(tmp_path / "changes.sqlite3")
    seq = journal.begin("a", 1, "UPSERT", hashlib.sha256(b"a").hexdigest())
    entry = journal.pending()[0]
    assert entry.sequence == seq
    assert isinstance(entry.created, float)
    assert entry.created > 0


def test_terminal_closure_requires_migration(tmp_path):
    journal = legacy_v1(tmp_path / "changes.sqlite3")
    seq = journal.begin("a", 1, "DELETE")
    with pytest.raises(ValueError, match="migration"):
        journal.close_terminal(seq, "ABANDONED", "canonical absent")
    assert journal.pending()[0].state == "INTENT"


def test_v2_closure_is_idempotent_and_not_pending(tmp_path):
    journal = ChangeJournal(tmp_path / "changes.sqlite3")
    seq = journal.begin("a", 1, "DELETE")
    assert migrate_v2(journal.path) == "ALREADY_V2"
    journal.close_terminal(seq, "ABANDONED", "not published")
    journal.close_terminal(seq, "ABANDONED", "not published")
    assert journal.pending() == ()
    with pytest.raises(ValueError, match="transition"):
        journal.close_terminal(seq, "SUPERSEDED", "newer canonical")


def test_indexed_cannot_be_reclosed(tmp_path):
    journal = ChangeJournal(tmp_path / "changes.sqlite3")
    seq = journal.begin("a", 1, "DELETE")
    journal.published(seq)
    journal.indexed(seq)
    migrate_v2(journal.path)
    with pytest.raises(ValueError, match="transition"):
        journal.close_terminal(seq, "ABANDONED", "wrong")
