# C207 — FTS5 publish receipt and SQLite journal validation (2026-10-28)

Scope: `experiment/fts5-indexport-c198`, active Memory branch base, VM100 isolated checkout. No merge, activation, or X399 wake.

## Added
- `PublishReceipt(state, generation, source_digest, error)` for the experimental verified adapter's `rebuild_with_receipt`.
- Outcomes:
  - `PUBLISHED` only after a successful rebuild and matching manifest digest.
  - `NOT_PUBLISHED` when replacement fails and the old generation remains active.
  - `PUBLISHED_UNCONFIRMED` when the new generation+digest is visible after a failure (e.g., directory fsync). This is **not** proof of durability.
  - `UNKNOWN` if evidence is incomplete, contradictory or unreadable.
- The base adapter now checks the staging SQLite DB using `PRAGMA integrity_check`, checkpoints a staging WAL if present, and `fsync`s the standalone staging database file before `os.replace` and parent directory fsync.

## Verified on VM100
- Native index journal mode currently `delete`; SQLite integrity `ok`. WAL checkpoint is defensive and has not been exercised against a live WAL-mode staging database under contention.
- Three receipt tests passed (normal, pre-replace injection, post-replace fsync failure).
- Eight targeted C204/C206/C207 tests passed in 0.20 s.
- Full suite: **3214 passed, 26 skipped, 3 xfailed, 12 subtests passed in 91.51 s**. Log `~/eidolon-validation/memory-c198-port/c207-regression.log`.

## Caveats before any merge
- `PUBLISHED_UNCONFIRMED` is visible but durability may be unknown after sudden power loss; neither synthetic exception nor a successful fsync is a proof against all hardware failure.
- The receipt compares manifest digest from an initial observation; canonical source changes in between require higher-level writer locking or revalidation.
- A physical power interruption, WAL-mode checkpoint failure and stale-open-handle race remain to be tested.
- Never blindly retry an uncertain publish; first re-read generation, manifest digest, and SQLite integrity, then choose a safe reconciliation.
- Multi-profile isolation and worker-facing policy still require review; experimental adapter is not wired to any active service.
