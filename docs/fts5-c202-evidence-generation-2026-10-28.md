# C202 — FTS5 verified evidence and generation experiment

Date: 2026-10-28. Branch: `experiment/fts5-indexport-c198` from active `refactor/architecture-v1`.
Experimental code: `core/indexing/fts5_verified_experimental.py`.
This is not registered in the Memory runtime, deployed or merged.

## Implemented (experimental)
- Explicit managed alias `eidolon_...`, with persisted random generation identity.
- Atomic SQLite transaction for indexing the document and its evidence tuple
  (information_id, revision, canonical_sha256, generation).
- Evidence `IndexEvidence` returned by `upsert_verified` and read by `evidence_for`.
- Cursor-paginated `IndexInventoryPage`; generation fence rejects stale cursors.
- Ordinary unverified `upsert` clears any previous evidence for its ID.
- `rebuild` rotates generation and discards old evidence. The canonical Markdown remains the truth.
- A dedicated private alias is required per scope; no runtime registration.

## Executed on Core VM100
- Targeted C202: 10 passed (generation persistence and rotation, verified write/readback, stale proof denial, pagination, rejected authorization, real JournalUpsertWorker replay on disposable canonical storage).
- Full repository suite, strict `umask 077`: **3201 passed, 26 skipped, 3 xfailed, 12 subtests passed in 91.28s**.
- Full log on VM100: `~/eidolon-validation/memory-c198-port/c202-regression.log`.

## Not established (must not deploy)
- No hard power-loss test and no guarantee of cross-process generation fencing. Reading
  generation uses a separate SQLite connection and is not yet protected against a concurrent rebuild.
- The worker's canonical digest is *trusted input* to the adapter; the existing
  `JournalUpsertWorker` validates it against canonical bytes before calling the index.
  This adapter alone does NOT authenticate origin or verify the filesystem.
- No audit of concurrent rebuild/in-flight upsert, schema upgrades, corrupted provenance,
  filtered index per user, secure OS file ownership, stale symlink and hardlink races,
  worker delete/reconcile semantics or performance under load.
- The existing `SqliteFts5Index` base schema and atomic staging are inherited; this
  is not a drop-in replacement for Qdrant's multi-generation collection protocol.
- Any runtime wiring requires explicit isolated integration review and permissions.
