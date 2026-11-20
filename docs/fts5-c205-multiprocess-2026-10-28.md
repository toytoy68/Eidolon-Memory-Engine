# C205 — FTS5 multiprocess race and abrupt-exit validation

Date: 2026-10-28. VM100 isolated checkout of `experiment/fts5-indexport-c198` based on active Memory branch `refactor/architecture-v1`. X399 not used; no production deployment or merge.

## Executed
New test file: `tests/test_fts5_multiprocess_c205.py`.
- Three **separate spawned processes** use the same disposable SQLite index: one performs 10 canonical rebuilds; two run 30 verified upserts each. All children exit cleanly. The final inventory is checked for evidence-generation and revision consistency.
- A child exits with `os._exit(137)` after writing a **not-yet-committed** generation change inside SQLite. A fresh process reopening the index sees the previous generation. `PRAGMA integrity_check` reports `ok`.
- The two-test campaign passed eight consecutive repetitions (16 test executions), plus the initial targeted run.
- Complete repo suite with `umask 077`: **3208 passed, 26 skipped, 3 xfailed, 12 subtests passed in 90.32 s**.
- Log: `~/eidolon-validation/memory-c198-port/c205-regression.log`; per-run targets `/tmp/eidolon-c205-pass-1.log` through `-8.log`.

## Residual risks
- This is **cooperating-process locking on a local POSIX filesystem**. An uncooperative writer or a raw base `SqliteFts5Index` may bypass the lock.
- Abrupt-exit injection was inside an uncommitted transaction, **not precisely during os.replace**, not a hard power loss, and not evidence of storage durability under electrical failure.
- Tests do not verify write receipt durability across fsync or journal replay after actual unclean VM reboot.
- Future review must address alias initialization races, stale SQLite file descriptors across atomic replacement, WAL sidecars, symlinks, crash during rebuild publish, authorization per profile, and stress across CPU/FS types.
- The experimental adapter remains explicitly NOT wired into the production runtime.
