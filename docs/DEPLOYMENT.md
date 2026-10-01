# Deployment and rollback — architecture v1 candidate

## Scope

Updated 2026-10-01, audited code `a779c9d`. Read
[AUDIT-2026-10-01.md](AUDIT-2026-10-01.md) before rollout. Known blockers:
Thread FAILED operations are omitted by `recover-all`; the format inventory
omits `thread-delete-v1`; migration archives deletion receipts without restoring
their active identity reservations. T-048/T-021 are pending. A zero exit code
from the current recovery CLI is not permission to restart writers.

The new repositories coordinate linked Thread creation and status changes with
isolated journals and explicit recovery; see THREAD_RECOVERY.md. New core
Information deletion requests have an explicit `APPLYING_DELETE` journal and
can be resumed after a process crash. Older inconsistent requests still need
human review. Historical data is not migrated. No automatic background
recovery job is installed.

The historical controller shares the Working lock with `memory-relations` and
refuses core Persistent data, but its Event and Review writes do not have the
new multi-file journal. Do not run historical writers against core Persistent
data. Shared network filesystems are not a supported deployment target for
these locks.

## Baseline backup

The remote tag `backup/pre-audit-fixes-b25da00` identifies the pre-change code.
A verified Git bundle is also retained on the development PC. Neither includes
ignored runtime data on the Debian host. A server backup is required before
updating production.

## Debian procedure

1. Identify and stop all processes writing the engine's data. Record the actual
   service names and restart commands; the repository defines no systemd units.
   `python -B -m tools.writer_inventory` lists matching running commands and
   configured systemd/cron entries without showing full arguments. It is only
   a hint: inspect other services, custom jobs and the effective data root.
2. Inspect `git status --short`, `git rev-parse HEAD`, and the active branch in
   `/opt/eidolon-memory-engine`. Preserve any uncommitted changes; do not reset.
3. Create a timestamped backup outside the engine directory containing the entire
   engine checkout (including `.git`, configuration and runtime memory), and any
   external data root configured through `MEMORY_ENGINE_ROOT`. Check the archive
   listing and checksum. Keep the services stopped while backing up.
4. Fetch `origin`, inspect the incoming commits, and fast-forward only to the
   exact reviewed commit on `refactor/architecture-v1`. Stop if histories diverge.
5. With the existing virtual environment, install the declared development
   dependencies if needed and run `python -m pytest -p no:cacheprovider` with
   `MEMORY_ENGINE_ROOT` pointing to an isolated temporary directory and
   `PYTHONDONTWRITEBYTECODE=1`. Include the five multiprocessing concurrency
   tests that could not run in the restricted development environment. Never
   run regression fixtures on live memory.
   On a stopped copy, `python -B -m tools.vm_acceptance --source COPIE --workdir
   DOSSIER_VIDE` reports the writer candidates, formats, hash-verified restore,
   five concurrency tests and four separate read-only audit results (including
   Information write journals). Review
   the full JSON report and every candidate before treating an OK as evidence.
6. On the isolated copy, inspect pending Operation records and test
   `python -m core.operations.cli recover-all` after keeping a restorable copy.
   The command writes to finish pending records and must not be run on the live
   tree while old writers are active. Audit pending Information deletions with
   `python -m core.information.deletion_recovery --root /path/to/copy`.
   Its `--apply` form mutates the copy and resumes only supported
   `APPLYING_DELETE` requests; review its report before any live run.
7. Before restarting a service that can write, use the proposed recovery gate
   below on the stopped live data, after the copy has passed its rehearsal.
   Review each report and keep writers stopped on any unresolved conflict.
   Then restart only the previously identified services, check their
   status/logs and perform a read-only application smoke test. Do not enable
   client writes until the gate and smoke test pass.

## Proposed startup recovery gate (not installed)

Before enabling any core writer after a restart, stop all writers and preserve
the current data state. The CLI `recover-all` processes Thread linked creations,
status changes, deletions, then Information writes. This ordering is implemented,
not a proof that every cross-family dependency is resolved. It also omits
FAILED Thread records. Inspect all persistent operation states independently
and keep writers stopped until T-048 provides a complete tested gate.
Audit deletion receipts next, then review
whether to run deletion recovery with `--apply` on the stopped data. If either
recovery reports a blocked record, or a FAILED/unreadable/unresolved record
remains, keep writers stopped and investigate. This
ordering needs validation with the actual Debian services, storage paths and
representative data; it is not a systemd unit or an automatic deletion policy.

## Rollback

Stop writers first. Keep a separate copy of the failed deployment and all new
runtime data. Restore the verified pre-deployment archive and its original
configuration, then restart the recorded services. Restoring old runtime data
would discard writes made after the backup; inspect and preserve those writes
before deciding to restore data. The Git tag alone rolls back code, not data.

## Remaining work

- Operational rollout of explicit Thread and deletion recovery (implemented
  for the supported new operations; no boot ordering configured yet).
- Explicit migration between legacy CLI formats and new repositories.
- Editable note views and migration of legacy CLI front-matter documents.
- Validate power-loss durability and reader consistency across multi-file
  operations on the Debian storage stack; process-crash tests cover linked
  Thread creation and each persisted Information deletion boundary separately.
- Integration tests using representative user datasets.
- Debian validation and application smoke tests on the actual host.

Human notes in project dossiers must be backed up, including custom output paths
outside the engine root. These notes cannot be reconstructed from canonical objects.
