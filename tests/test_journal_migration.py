"""Offline journal migration regression tests."""
import hashlib
import sqlite3
import pytest
from core.indexing.change_journal import ChangeJournal
from core.indexing.journal_migration import migrate_v2
from tests.legacy_journal_fixture import legacy_v1


def test_migration_preserves_rows_and_is_idempotent(tmp_path):
    path = tmp_path / "journal.sqlite3"
    journal = legacy_v1(path)
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
    path.chmod(0o600)
    with pytest.raises(ValueError, match="unknown journal schema"):
        migrate_v2(path)
    with sqlite3.connect(path) as db:
        assert [r[1] for r in db.execute("PRAGMA table_info(intents)")] == ["x"]


def test_native_v2_sets_version_without_rewriting_existing_v1(tmp_path):
    native = tmp_path / "native.sqlite3"
    ChangeJournal(native)
    with sqlite3.connect(native) as db:
        assert db.execute("PRAGMA user_version").fetchone()[0] == 2
        assert "terminal_reason" in {r[1] for r in db.execute("PRAGMA table_info(intents)")}

    from tests.legacy_journal_fixture import legacy_v1
    old = tmp_path / "legacy.sqlite3"
    legacy_v1(old)
    with sqlite3.connect(old) as db:
        assert db.execute("PRAGMA user_version").fetchone()[0] == 0
        assert "terminal_reason" not in {r[1] for r in db.execute("PRAGMA table_info(intents)")}

def test_open_existing_journal_missing_index_does_not_repair(tmp_path):
    path = tmp_path / "legacy.sqlite3"
    from tests.legacy_journal_fixture import legacy_v1
    legacy_v1(path)
    with sqlite3.connect(path) as db:
        db.execute("DROP INDEX intent_state_seq")
    with pytest.raises(ValueError, match="explicit repair"):
        ChangeJournal(path)
    with sqlite3.connect(path) as db:
        assert db.execute("PRAGMA user_version").fetchone()[0] == 0
        assert db.execute("SELECT name FROM sqlite_master WHERE type='index' AND name='intent_state_seq'").fetchone() is None
