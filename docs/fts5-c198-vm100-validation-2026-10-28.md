# Eidolon Memory FTS5 C198 — independent VM100 validation

Date: 2026-10-28; repository: toytoy68/Eidolon-Memory-Engine.
Branch: `experiment/fts5-indexport-c198`, base `refactor/architecture-v1`.
Source: Claude patch 0003 from Eidolon-Bootstrap-Framework C198.

## Environment
Debian 13 Core VM100 (not Memory production), independent checkout at
`~/eidolon-validation/memory-c198-port`; Python 3.13, fresh virtual environment.
Requirements installed from repository's `requirements-dev.txt` and `requirements-qdrant.txt`.

## Verified
- Python source compilation of two newly added files: passed.
- Targeted `tests/test_fts5_index.py`: 8 passed in 0.51 s.
- Full suite `umask 077; .venv/bin/python -m pytest -q`:
  **3185 passed, 26 skipped, 3 xfailed, 12 subtests passed in 90.95 s**.
- The first full-suite attempt in the initial fresh venv did not collect due to missing
  cryptography and qdrant_client. Dependencies installed.
- The second attempt after dependency install found 2 failures caused by world/group
  writable temporary runtime snapshots with the default VM umask, unrelated to the
  new FTS5 adapter. Both passed individually under `umask 077`; the third full run
  passed. Original failure logs were retained.
- No backend runtime, journal or worker wiring changed. No services restarted.
- EidolonOS X399 was not powered on; this was performed on Core VM100.

## Blockers
Do not merge/deploy pending separate tests of journal/worker replay, access isolation,
crash/rebuild concurrency, realistic corpus, and performance under the target workload.
The two September-main PRs #1 and #2 remain obsolete drafts.
