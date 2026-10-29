# C206 — SQLite snapshot and index publication boundary (2026-10-28)

VM100 isolated checkout of `experiment/fts5-indexport-c198`. No deployment, no X399 wake.

## Fault injection
- Before `os.replace`: synthetic exception, previous generation remains readable, newly ingested canonical document not visible until successful rebuild.
- Open SQLite handle kept across `os.replace`: the handle still reads old snapshot (one document), whereas a new connection reads two. Do not reuse stale open handles for evidence.
- After `os.replace` but during directory `fsync`: synthetic exception. Method reports failure, but in-process reopened index contains the new document. Publication outcome is **uncertain**, not safely rolled back. A real power failure was not executed.
- These are synthetic failure injections against disposable indices. No actual hard power interruption or kernel crash.

## Validation
New tests: `tests/test_fts5_swap_c206.py`, `tests/test_fts5_publish_boundary_c206.py`.
Targeted: 3 passed in 0.07 s.
Complete suite on VM100 under `umask 077`: **3211 passed, 26 skipped, 3 xfailed, 12 subtests passed in 91.46 s**.
Log: `~/eidolon-validation/memory-c198-port/c206-regression.log`.

## Required follow-up before any merge
- Design explicit publish receipt / after-exception read-back, using generation+manifest digest as evidence of which snapshot became active. Never retry blindly on uncertain publish.
- Investigate stale SQLite connections, WAL sidecar behavior and locks on POSIX inode replacement.
- Add explicit fsync of staging DB and WAL checkpoint before replacement, plus crash recovery tests.
- Prove authorization and indexed profile partitioning. Do not claim production durability from this test.
