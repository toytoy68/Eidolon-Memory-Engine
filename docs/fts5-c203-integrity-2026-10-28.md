# C203 — FTS5 evidence integrity hardening (2026-10-28)

Branch `experiment/fts5-indexport-c198` based on active Memory `refactor/architecture-v1`. VM100 isolated checkout, production unchanged.

## Confirmed regression and correction
Three C203 corruption probes were added. Before the fix, changing the evidence revision from 1 to 99 directly in SQLite was silently accepted: the probe **failed** as expected, while generation mismatch and orphaned evidence were rejected.

The adapter's `evidence_for()` now loads the matching indexed document and refuses mismatching identity or revision. It also fails closed if its JSON cannot be decoded.

## Validation
- Before fix: 1 failed, 2 passed (expected failing adversarial probe).
- After fix: 13 targeted integrity, worker, generation and evidence tests passed in 0.13 s.
- Full Memory suite, `umask 077`: **3204 passed, 26 skipped, 3 xfailed, 12 subtests passed in 91.33s**.
- Log: `~/eidolon-validation/memory-c198-port/c203-regression.log`.

## Outstanding critical work
The generation and evidence are not yet guarded against a concurrent `os.replace` rebuild from another process. Nested SQLite connections can observe different generations. Do not deploy or merge before introducing a single coherent transaction and cross-process rebuild/write fencing, with fault injection tests; then verify profile-bound authorization and crash recovery. This suite did not demonstrate that concurrent rebuild is safe.
