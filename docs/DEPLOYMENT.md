# Deployment and rollback â€” first audit correction batch

## Scope

This batch protects cooperative filesystem writers, Operation identities and
immutable plans, pending deletion decisions, Event validation, and query filters.
Historical data is not migrated. A subsequent batch adds explicit Thread recovery;
see THREAD_RECOVERY.md. No automatic background recovery job is installed.

The old CLI controller does not participate in repository locks. Do not run it
concurrently with repository writers. Shared network filesystems are not a
supported deployment target for these locks.

## Baseline backup

The remote tag `backup/pre-audit-fixes-b25da00` identifies the pre-change code.
A verified Git bundle is also retained on the development PC. Neither includes
ignored runtime data on the Debian host. A server backup is required before
updating production.

## Debian procedure

1. Identify and stop all processes writing the engine's data. Record the actual
   service names and restart commands; the repository defines no systemd units.
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
   `PYTHONDONTWRITEBYTECODE=1`. Never run regression fixtures on live memory.
6. Restart only the previously identified services. Check their status/logs and
   perform a read-only application smoke test before permitting writes.

## Rollback

Stop writers first. Keep a separate copy of the failed deployment and all new
runtime data. Restore the verified pre-deployment archive and its original
configuration, then restart the recorded services. Restoring old runtime data
would discard writes made after the backup; inspect and preserve those writes
before deciding to restore data. The Git tag alone rolls back code, not data.

## Remaining work

- Operational rollout of explicit Thread recovery (implemented; see THREAD_RECOVERY.md).
- Explicit migration between legacy CLI formats and new repositories.
- Editable note views and migration of legacy CLI front-matter documents.
- Directory fsync and crash consistency across multi-file operations.
- Integration tests using representative user datasets.
- Debian validation and application smoke tests on the actual host.
