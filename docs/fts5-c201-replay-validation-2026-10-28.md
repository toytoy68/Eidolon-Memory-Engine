# C201 — Offline FTS5 replay tests on VM100 (2026-10-28)

Base: `refactor/architecture-v1`, feature branch
`experiment/fts5-indexport-c198`; original Claude C198 adapter.

Exact updated GitHub branch cloned locally on VM100, Debian 13, isolated Python
venv. No Memory production services touched and X399 remains off.

## Tests added
`tests/test_fts5_offline_replay_c201.py`
1. Rebuilding a derived FTS5 index after a canonical memory revision removes
   obsolete matches and restores results from current Markdown.
2. A malformed canonical document refuses a rebuild without destroying the
   previous index (old index remains readable).
3. Reopen a rebuilt index: data remains accessible and SQLite file permissions
   remain private.

Local targeted run together with C200 safety tests: **6 passed in 0.44 s**.

Full suite, strict `umask 077`:
**3191 passed, 26 skipped, 3 xfailed, 12 subtests passed in 90.13 s**.
Log: `~/eidolon-validation/memory-c198-port/c201-regression.log`.

## Critical limitation
These are offline rebuild and safety-gate tests. The FTS5 adapter currently
implements basic `IndexPort` but lacks the worker's required verification
methods `active_generation`, `evidence_for`, `upsert_verified`,
`inventory_page`, stable `embedding_id` and `alias`. It **must not** be
plugged into `JournalUpsertWorker` without a vetted provenance-aware
implementation, replay and authorisation tests. No runtime wiring or merge.
