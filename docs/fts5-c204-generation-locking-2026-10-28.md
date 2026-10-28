# C204 — Generation locking experiment (2026-10-28)

Isolated Core VM100; branch `experiment/fts5-indexport-c198`, active Memory base `refactor/architecture-v1`. No production deployment.

## Change
A reentrant in-process RLock and a cross-process Linux `flock` lockfile (`*.generation.lock`) wrap FTS5 verified evidence reads/writes, inventory, generation checks and rebuild, to serialize cooperative instances on one local filesystem. Nested calls reuse the outer lock.

## Executed
- Generation race test: two separate instances on one FTS5 file, 12 rebuilds concurrently with 60 verified upserts; completed without exception. Evidence either remains consistent with the active generation or disappears after rebuild.
- Nested lock test: verified upsert, readback and inventory completed without deadlock.
- Earlier 13 targeted C202/C203 tests passed.
- Full suite: **3206 passed, 26 skipped, 3 xfailed, 12 subtests passed in 90.84 seconds**, VM100 log `~/eidolon-validation/memory-c198-port/c204-regression.log`.

## Important limitations
This is NOT yet a proven durable production locking design. Testing covered concurrent threads/instances, not separate processes or hard power loss. All callers must cooperate with the same flock; a raw base adapter bypasses it. Initialization and SQLite WAL sidecar/atomic replacement interactions require review. A stale open SQLite connection or out-of-band file edit may still cause inconsistency; tests must be extended. Lockfile location assumes a local POSIX filesystem; network storage (e.g. NFS) is out of scope. No multi-profile data isolation demonstrated.
