"""Legacy v1 journal fixture for migration regression tests only."""
import sqlite3
from core.indexing.change_journal import ChangeJournal


def legacy_v1(path):
    with sqlite3.connect(path) as db:
        db.execute("""CREATE TABLE intents (
            seq INTEGER PRIMARY KEY AUTOINCREMENT,
            information_id TEXT NOT NULL,
            revision INTEGER NOT NULL,
            operation TEXT NOT NULL,
            canonical_sha256 TEXT,
            state TEXT NOT NULL CHECK(state IN ('INTENT','PUBLISHED','INDEXED')),
            created REAL NOT NULL,
            updated REAL NOT NULL
        )""")
        db.execute("CREATE INDEX intent_state_seq ON intents(state,seq)")
    path.chmod(0o600)
    return ChangeJournal(path)
