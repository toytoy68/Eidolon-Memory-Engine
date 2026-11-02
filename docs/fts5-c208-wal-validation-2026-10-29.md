# C208 — SQLite WAL staging and publication receipts

Date: 2026-10-29. Branch: `experiment/fts5-indexport-c198`, derived from active Memory architecture. Executed in a separate Core VM100 checkout, not on X399.

## Executed
- Normal publication receipt agrees with canonical manifest digest; rebuild changes generation.
- Forced `PRAGMA journal_mode=WAL` on the disposable staging SQLite database; rebuild, checkpoint/publish, reopen and `PRAGMA integrity_check` succeeded.
- Synthetic failure before file replacement returns `NOT_PUBLISHED` and retains the original generation.
- New targeted tests: **3 passed**.
- Full suite: **3217 passed, 26 skipped, 3 xfailed, 12 subtests passed in 91.19s**.
- Log: `~/eidolon-validation/memory-c198-port/c208-regression.log`.

## Remaining gaps
- WAL test did **not** contend with an active WAL writer or simulate sudden power loss. The staging DB is closed before publishing. Hot WAL checkpoint, stale open connections during swap, and filesystem durability under crash require separate tests.
- Receipt is an observation of active generation and manifest digest, **not** an end-to-end proof of canonical-write durability or filesystem reliability.
- Raw adapters not honoring the generation lock can bypass the serialized path.
- No Memory runtime activation, no production merge, and X399 remains off.
