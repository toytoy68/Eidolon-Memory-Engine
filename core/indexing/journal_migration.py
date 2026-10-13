"""Explicit, offline migration of the advisory index journal to schema v2.

This migration must run only on a stopped writer, after a verified backup.
It does not change canonical Markdown, Qdrant, or running services.
"""
from contextlib import closing
from pathlib import Path
import os
import sqlite3
import stat

OLD = "state IN ('INTENT','PUBLISHED','INDEXED')"
NEW = "state IN ('INTENT','PUBLISHED','INDEXED','ABANDONED','SUPERSEDED')"


def migrate_v2(path):
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise ValueError("journal must be a regular file")
    if not stat.S_ISREG(path.stat().st_mode) or stat.S_IMODE(path.stat().st_mode) & 0o077:
        raise ValueError("journal permissions must be private")
    if stat.S_IMODE(path.parent.stat().st_mode) & 0o077:
        raise ValueError("journal parent must be private")
    with closing(sqlite3.connect(str(path), timeout=1)) as db:
        db.execute("PRAGMA busy_timeout=1000")
        db.execute("PRAGMA synchronous=FULL")
        db.execute("BEGIN IMMEDIATE")
        try:
            row = db.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='intents'").fetchone()
            if not row or not row[0]:
                raise ValueError("missing journal schema")
            schema = row[0]
            if NEW in schema:
                db.commit()
                return "ALREADY_V2"
            if OLD not in schema:
                raise ValueError("unknown journal schema")
            columns = [r[1] for r in db.execute("PRAGMA table_info(intents)")]
            expected = ["seq","information_id","revision","operation","canonical_sha256","state","created","updated"]
            if columns != expected:
                raise ValueError("unknown journal columns")
            sequence_row = db.execute("SELECT seq FROM sqlite_sequence WHERE name='intents'").fetchone()
            prior_sequence = sequence_row[0] if sequence_row else 0
            db.execute("""CREATE TABLE intents_v2 (
                seq INTEGER PRIMARY KEY AUTOINCREMENT,
                information_id TEXT NOT NULL,
                revision INTEGER NOT NULL,
                operation TEXT NOT NULL,
                canonical_sha256 TEXT,
                state TEXT NOT NULL CHECK(state IN ('INTENT','PUBLISHED','INDEXED','ABANDONED','SUPERSEDED')),
                created REAL NOT NULL,
                updated REAL NOT NULL,
                terminal_reason TEXT
            )""")
            db.execute("""INSERT INTO intents_v2(seq,information_id,revision,operation,canonical_sha256,state,created,updated)
                          SELECT seq,information_id,revision,operation,canonical_sha256,state,created,updated FROM intents""")
            before = db.execute("SELECT COUNT(*) FROM intents").fetchone()[0]
            after = db.execute("SELECT COUNT(*) FROM intents_v2").fetchone()[0]
            if before != after:
                raise ValueError("migration count mismatch")
            db.execute("DROP TABLE intents")
            db.execute("ALTER TABLE intents_v2 RENAME TO intents")
            migrated_max = db.execute("SELECT COALESCE(MAX(seq),0) FROM intents").fetchone()[0]
            db.execute("DELETE FROM sqlite_sequence WHERE name='intents'")
            db.execute("INSERT INTO sqlite_sequence(name,seq) VALUES ('intents',?)",
                       (max(prior_sequence, migrated_max),))
            db.execute("CREATE INDEX IF NOT EXISTS intent_state_seq ON intents(state,seq)")
            db.execute("PRAGMA user_version=2")
            db.commit()
            return "MIGRATED_V2"
        except BaseException:
            db.rollback()
            raise
