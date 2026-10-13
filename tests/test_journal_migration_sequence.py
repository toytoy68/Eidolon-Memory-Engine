"""Preserve monotonic journal sequence IDs across a v1 to v2 migration."""
import sqlite3

from core.indexing.change_journal import ChangeJournal
from core.indexing.journal_migration import migrate_v2
from tests.legacy_journal_fixture import legacy_v1


def test_migration_preserves_high_water_after_compaction(tmp_path):
    path = tmp_path / "journal.sqlite3"
    journal = legacy_v1(path)
    numbers = [journal.begin(f"doc-{i}", 1, "DELETE") for i in range(5)]
    with sqlite3.connect(path) as db:
        db.execute("DELETE FROM intents WHERE seq >= ?", (numbers[-2],))
    assert migrate_v2(path) == "MIGRATED_V2"
    newer = journal.begin("new", 1, "DELETE")
    assert newer > numbers[-1]
    assert migrate_v2(path) == "ALREADY_V2"


def test_migration_keeps_sequence_after_empty_compacted_table(tmp_path):
    path = tmp_path / "journal.sqlite3"
    journal = legacy_v1(path)
    old = journal.begin("old", 1, "DELETE")
    with sqlite3.connect(path) as db:
        db.execute("DELETE FROM intents")
    migrate_v2(path)
    assert journal.begin("new", 1, "DELETE") > old
