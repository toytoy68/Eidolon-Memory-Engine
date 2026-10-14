# ==========================================================
# Projet      : Eidolon Memory Engine
# Organisation: Eidolon Core Technologies (ECT)
# Fichier     : tests/claude_memory_eval/test_journal_crash_probes_g218.py
# Description : Audit Claude G218-3 : plantages pendant l'initialisation et la migration, verrous multiprocessus
# Standard    : Eidolon Presentation Standard v1
# ==========================================================
"""A child process is killed (os._exit) at a precise SQL statement, through a sqlite3.connect wrapper installed
in the child only. The parent then checks that the journal is intact and usable. GPT's files are not modified."""
import multiprocessing
import os
import sqlite3

import pytest

from core.indexing.change_journal import ChangeJournal
from core.indexing.journal_migration import migrate_v2

V1 = """CREATE TABLE intents (seq INTEGER PRIMARY KEY AUTOINCREMENT, information_id TEXT NOT NULL,
    revision INTEGER NOT NULL, operation TEXT NOT NULL, canonical_sha256 TEXT,
    state TEXT NOT NULL CHECK(state IN ('INTENT','PUBLISHED','INDEXED')), created REAL NOT NULL,
    updated REAL NOT NULL)"""


def v1(path, rows=3):
    with sqlite3.connect(path) as raw:
        raw.execute(V1)
        raw.execute("CREATE INDEX intent_state_seq ON intents(state,seq)")
    os.chmod(path, 0o600)
    journal = ChangeJournal(path)
    return [journal.begin(f"doc-{i}", 1, "DELETE") for i in range(rows)]


def state(path):
    with sqlite3.connect(path) as raw:
        return (raw.execute("SELECT sql FROM sqlite_master WHERE name='intents'").fetchone(),
                raw.execute("PRAGMA user_version").fetchone()[0],
                raw.execute("SELECT * FROM intents ORDER BY seq").fetchall() if raw.execute(
                    "SELECT 1 FROM sqlite_master WHERE name='intents'").fetchone() else None,
                raw.execute("PRAGMA integrity_check").fetchone()[0])


class _Dying:
    """Connection proxy: dies (os._exit) when a statement containing ``needle`` is about to run."""

    def __init__(self, conn, needle):
        self._conn, self._needle = conn, needle

    def execute(self, sql, *args):
        if self._needle in sql:
            os._exit(17)
        return self._conn.execute(sql, *args)

    def __getattr__(self, name):
        return getattr(self._conn, name)

    def __enter__(self):
        self._conn.__enter__()
        return self

    def __exit__(self, *exc):
        return self._conn.__exit__(*exc)


def _die_in(target, path, needle):
    real = sqlite3.connect
    sqlite3.connect = lambda *a, **k: _Dying(real(*a, **k), needle)
    target(path)
    os._exit(0)                                                    # needle never reached


def crash(target, path, needle):
    process = multiprocessing.get_context("fork").Process(target=_die_in, args=(target, path, needle))
    process.start()
    process.join(30)
    return process.exitcode


@pytest.mark.parametrize("needle", ["CREATE TABLE intents_v2", "INSERT INTO intents_v2", "DROP TABLE intents",
                                    "ALTER TABLE intents_v2", "INSERT INTO sqlite_sequence", "PRAGMA user_version=2"])
def test_a_crash_at_any_migration_step_leaves_the_v1_journal_intact_and_migratable(tmp_path, needle):
    path = tmp_path / "changes.sqlite3"
    seqs = v1(path)
    before = state(path)
    assert crash(migrate_v2, path, needle) == 17
    assert state(path) == before                                   # rolled back: same schema, rows, integrity
    assert migrate_v2(path) == "MIGRATED_V2"
    assert ChangeJournal(path).begin("new", 1, "DELETE") == seqs[-1] + 1


@pytest.mark.parametrize("needle", ["CREATE TABLE IF NOT EXISTS intents", "CREATE INDEX", "PRAGMA user_version=2"])
def test_a_crash_while_creating_a_new_journal_leaves_a_recoverable_file(tmp_path, needle):
    path = tmp_path / "changes.sqlite3"
    assert crash(ChangeJournal, path, needle) == 17
    assert os.stat(path).st_mode & 0o777 == 0o600                  # the file exists, private
    journal = ChangeJournal(path)                                  # reopening finishes the job
    journal.close_terminal(journal.begin("doc", 1, "DELETE"), "ABANDONED", "test")
    schema, version, rows, integrity = state(path)
    assert "ABANDONED" in schema[0] and integrity == "ok" and len(rows) == 1


def test_a_crash_before_the_version_is_written_still_ends_as_version_2(tmp_path):
    """M13 (G218), fixed in 975ca6c: table, index and version are created in one transaction."""
    path = tmp_path / "changes.sqlite3"
    assert crash(ChangeJournal, path, "PRAGMA user_version=2") == 17
    ChangeJournal(path)
    assert state(path)[1] == 2


def _migrate(path, queue):
    try:
        queue.put(migrate_v2(path))
    except Exception as exc:
        queue.put(type(exc).__name__)


def test_concurrent_migrations_never_corrupt_and_migrate_once(tmp_path):
    path = tmp_path / "changes.sqlite3"
    v1(path, rows=50)
    context = multiprocessing.get_context("fork")
    queue = context.Queue()
    workers = [context.Process(target=_migrate, args=(path, queue)) for _ in range(4)]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join(30)
    results = sorted(queue.get(timeout=10) for _ in workers)
    assert results.count("MIGRATED_V2") == 1
    assert set(results) <= {"MIGRATED_V2", "ALREADY_V2", "OperationalError"}
    schema, version, rows, integrity = state(path)
    assert "ABANDONED" in schema[0] and version == 2 and len(rows) == 50 and integrity == "ok"
