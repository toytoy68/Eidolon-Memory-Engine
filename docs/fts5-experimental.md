# Experimental Markdown + SQLite FTS5 backend

This feature is **opt-in**. The existing `FilesystemBackend` and production
Memory Engine configuration are unchanged.

## Design

- Canonical source: existing human-readable Markdown files.
- Derived index: `history/search_fts5.sqlite3` (SQLite FTS5 / BM25).
- Every search result is reloaded through canonical `get()`; missing
  Markdown files are excluded.
- The index is fully reconciled on construction and can be manually rebuilt
  with `rebuild_index()`.
- Write operations performed through `FTS5Backend` update the derived index
  after the canonical write.

Example, in an isolated test environment:

```python
from pathlib import Path
from core.backend.fts5_backend import FTS5Backend

backend = FTS5Backend(
    persistent_root=Path("/tmp/eidolon-lab/persistent"),
    history_root=Path("/tmp/eidolon-lab/history"),
)
print(backend.rebuild_index())
print(backend.search("FastAPI dependency injection", {"limit": 5}))
```

## Safety and limitations

This is not yet production-ready. A Markdown file and its FTS5 entry are
**not one atomic transaction**. A crash between their writes may temporarily
produce stale or missing results. Initialization reconciles the index when
restarting through this class. The index is also not automatically updated
when another process bypasses this class and edits Markdown directly.

Concurrent writes to *different* memories were exercised experimentally
(120 threaded and 60 multiprocess operations), but same-ID concurrent updates,
process crash injection, database corruption recovery, privacy enforcement,
and large corpus scaling need more exhaustive qualification.

FTS5 is lexical, not semantic search. The prior benchmarks on 100 documents
used heading-derived queries, not held-out question-answer ground truth.
In that narrow experiment, Markdown+FTS5 achieved 93% Recall@5 and 2.53 ms
median latency against 86% and 20.80 ms for plain Markdown scanning.
Those measurements are not a verified end-to-end MemEval or PropMem score.

## Validation

```bash
python -m pytest -q tests/test_fts5_backend.py
python -m pytest -q
```

Do not merge or deploy this branch without a full integration and recovery
review. Never add private conversation content or credentials to Git.
