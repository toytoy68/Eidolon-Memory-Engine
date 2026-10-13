"""Tests for read-only reconciliation preview."""
import hashlib
import pytest

from core.indexing.change_journal import ChangeJournal
from core.indexing.reconcile_plan import Canonical
from core.indexing.reconcile_preview import preview_reconciliation


def test_recover_published_canonical_without_writing(tmp_path):
    journal = ChangeJournal(tmp_path / "changes.sqlite3")
    digest = hashlib.sha256(b"source").hexdigest()
    seq = journal.begin("doc", 1, "UPSERT", digest)
    created = journal.pending()[0].created
    result = preview_reconciliation(journal, {"doc": Canonical(1, digest)}, {},
                                    now=created + 2)
    assert [(a.kind, a.sequence) for a in result.actions] == [("MARK_PUBLISHED", seq)]
    assert journal.pending()[0].state == "INTENT"


def test_unpublished_intent_waits_before_grace(tmp_path):
    journal = ChangeJournal(tmp_path / "changes.sqlite3")
    journal.begin("doc", 1, "DELETE")
    created = journal.pending()[0].created
    result = preview_reconciliation(journal, {"doc": Canonical(1, "a" * 64)}, {"doc": 1},
                                    now=created + 2, grace_seconds=600)
    assert result.actions[0].kind == "WAIT"
    assert result.requires_review


def test_stale_intent_may_be_closed_after_grace(tmp_path):
    journal = ChangeJournal(tmp_path / "changes.sqlite3")
    journal.begin("doc", 1, "UPSERT", "a" * 64)
    created = journal.pending()[0].created
    result = preview_reconciliation(journal, {}, {}, now=created + 601)
    assert result.actions[0].kind == "CLOSE_ABANDONED"
    assert journal.pending()[0].state == "INTENT"


def test_reject_truncated_journal(tmp_path):
    journal = ChangeJournal(tmp_path / "changes.sqlite3")
    journal.begin("doc", 1, "DELETE")
    with pytest.raises(ValueError, match="truncated"):
        preview_reconciliation(journal, {}, {}, limit=1)


def test_reject_future_intent(tmp_path):
    journal = ChangeJournal(tmp_path / "changes.sqlite3")
    journal.begin("doc", 1, "DELETE")
    with pytest.raises(ValueError, match="timestamp"):
        preview_reconciliation(journal, {}, {}, now=1)
