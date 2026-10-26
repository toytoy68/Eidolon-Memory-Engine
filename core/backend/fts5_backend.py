"""Optional SQLite FTS5 index over canonical Markdown memories.

The Markdown backend remains authoritative. SQLite is disposable and is rebuilt
at startup to recover from interrupted writes and external file changes.
No production backend is changed by importing this module.
"""
from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path
from typing import Any

from .filesystem import FilesystemBackend
from .models import DeleteResult, Memory, SearchResult, StoreResult, UpdateResult


class FTS5Backend(FilesystemBackend):
    """Opt-in BM25 search index with canonical Markdown read-through."""

    def __init__(
        self,
        persistent_root: Path | None = None,
        history_root: Path | None = None,
    ) -> None:
        super().__init__(persistent_root=persistent_root, history_root=history_root)
        self.db_path = self.history_root / "search_fts5.sqlite3"
        self.rebuild_index()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path, timeout=30)
        connection.execute("PRAGMA busy_timeout=30000")
        connection.execute("PRAGMA journal_mode=WAL")
        return connection

    @staticmethod
    def _create_index(connection: sqlite3.Connection) -> None:
        connection.execute(
            "CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts USING "
            "fts5(information_id UNINDEXED, content, metadata, provenance)"
        )

    @staticmethod
    def _values(memory: Memory) -> tuple[str, str, str, str]:
        return (
            memory.information_id,
            str(memory.content if memory.content is not None else ""),
            json.dumps(memory.metadata, ensure_ascii=False, default=str),
            json.dumps(memory.provenance, ensure_ascii=False, default=str),
        )

    def _index_one(self, memory: Memory) -> None:
        with self._connect() as connection:
            self._create_index(connection)
            connection.execute(
                "DELETE FROM memories_fts WHERE information_id=?",
                (memory.information_id,),
            )
            connection.execute(
                "INSERT INTO memories_fts VALUES (?, ?, ?, ?)",
                self._values(memory),
            )

    def store(self, memory: Memory) -> StoreResult:
        result = super().store(memory)
        self._index_one(memory)
        return result

    def update(
        self, information_id: str, memory: Memory, previous_revision: int
    ) -> UpdateResult:
        result = super().update(information_id, memory, previous_revision)
        self._index_one(memory)
        return result

    def approve_delete(self, information_id: str, operation_id: str) -> DeleteResult:
        result = super().approve_delete(information_id, operation_id)
        with self._connect() as connection:
            self._create_index(connection)
            connection.execute(
                "DELETE FROM memories_fts WHERE information_id=?",
                (information_id,),
            )
        return result

    def rebuild_index(self) -> dict[str, Any]:
        """Reconcile a missing or stale index with canonical Markdown files.

        Call this during initialization or after restoring Markdown from backup.
        Index corruption beyond missing tables may require deleting the SQLite
        files and rebuilding them; never delete canonical Markdown for recovery.
        """
        memories = self.list(limit=1_000_000)
        with self._connect() as connection:
            self._create_index(connection)
            connection.execute("DELETE FROM memories_fts")
            connection.executemany(
                "INSERT INTO memories_fts VALUES (?, ?, ?, ?)",
                (self._values(memory) for memory in memories),
            )
        return {"status": "OK", "indexed": len(memories), "backend": "fts5"}

    def search(
        self, query: str, options: dict[str, Any] | None = None
    ) -> list[SearchResult]:
        terms = re.findall(r"\w+", query, flags=re.UNICODE)
        if not terms:
            return []
        expression = " OR ".join('"' + term + '"' for term in terms)
        limit = max(1, min(10_000, int((options or {}).get("limit", 100))))
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT information_id, bm25(memories_fts) FROM memories_fts "
                "WHERE memories_fts MATCH ? ORDER BY bm25(memories_fts) LIMIT ?",
                (expression, limit),
            ).fetchall()
        results: list[SearchResult] = []
        for information_id, rank in rows:
            memory = self.get(information_id)
            if memory is not None:
                results.append(SearchResult(memory=memory, score=-float(rank)))
        return results
