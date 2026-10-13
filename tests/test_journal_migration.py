"""Offline journal migration regression tests."""
import hashlib
import sqlite3
import pytest
from core.indexing.change_journal import ChangeJournal
from core.indexing.journal_migration import migrate_v2


def test_migration_preserves_rows_and_is_idempotent(tmp_path):
    path = tmp_path / "journal.sqlite3"
    journal = ChangeJournal(path)
    first = journal.begin("archive", 2, "UPSERT", hashlib.sha256(b"test").hexdigest())
    journal.published(first)
    second = journal.begin("other", 1, "DELETE")
    assert migrate_v2(path) == "MIGRATED_V2"
    assert migrate_v2(path) == "ALREADY_V2"
    with sqlite3.connect(path) as db:
        rows = db.execute("SELECT seq,information_id,state,terminal_reason FROM intents ORDER BY seq").fetchall()
        assert rows == [(first,"archive","PUBLISHED",None),(second,"other","INTENT",None)]
        db.execute("UPDATE intents SET state='ABANDONED',terminal_reason='not published' WHERE seq=?", (second,))
        db.execute("UPDATE intents SET state='SUPERSEDED',terminal_reason='newer revision' WHERE seq=?", (first,))
        db.commit()


def test_missing_file_does_not_create_database(tmp_path):
    path = tmp_path / "missing.sqlite3"
    with pytest.raises(ValueError):
        migrate_v2(path)
    assert not path.exists()


def test_rejects_public_database(tmp_path):
    path = tmp_path / "journal.sqlite3"
    ChangeJournal(path)
    path.chmod(0o644)
    with pytest.raises(ValueError, match="private"):
        migrate_v2(path)


def test_rejects_unknown_schema_without_mutation(tmp_path):
    path = tmp_path / "journal.sqlite3"
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE intents (x INTEGER)")
    with pytest.raises(ValueError, match="unknown journal schema"):
        migrate_v2(path)
    with sqlite3.connect(path) as db:
        assert [r[1] for r in db.execute("PRAGMA table_info(intents)")] == ["x"]
