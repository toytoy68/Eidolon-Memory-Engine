# Recoverable Thread operations

The filesystem coordinators connect Thread state, immutable Event and Operation
records. Linked creation, status changes and deletion use separate
`thread-create-v1`, `thread-status-v1` and `thread-delete-v1` journals. They are available through
`python -m core.operations.cli`; the status coordinator can also be injected into
`ThreadService`.

## Commands

```sh
python -m core.operations.cli change-status THREAD_ID VALIDATED --previous-revision 1 --operation-id UNIQUE_OPERATION_ID
python -m core.operations.cli delete-thread THREAD_ID --previous-revision 2 --operation-id UNIQUE_DELETE_ID
python -m core.operations.cli recover-all
```

A Thread must already exist and pass domain validation. The operation ID is a
caller-supplied idempotency key. Repeating the same command returns its original
result without another revision or Event. Reusing its ID for another command is
rejected. The default Event ID is derived deterministically from the operation ID.

Recovery is explicit: run `recover-all` before accepting mutations after a
process restart. It processes linked creations, then status changes, then
Thread deletions. No daemon
or scheduled recovery job is installed. The command returns a
nonzero exit status if a record needs intervention, while independent records are
still processed. Pending operations block new commands for the same Thread.
`recover-creations`, `recover` and `recover-deletions` remain available for separate families. The
CLI `create-linked` journals creation with an explicit timestamp and emits a
Thread `CREATED` Event; direct storage writes do not provide this guarantee.
An unfinished linked creation reserves its Information target for deletion:
approval checks the creation journal even before the Thread file exists.

## Protocol and guarantees

1. Validate the transition and persist exact before/after snapshots plus a hash.
2. Persist APPLYING.
3. Write the next Thread revision.
4. Write the deterministic Event, with the original transition timestamp.
5. Persist COMMITTED.

The Thread writer lock covers this sequence; nested repository locks use the
order Thread -> Operation -> Event. Abrupt process termination releases OS locks.
POSIX writers flush the file and the containing directory after replacement.
Windows uses file flush and atomic replacement; power-loss durability still
requires platform validation. Tests cover process termination, not power loss.
The linked creation path is exercised with hard process exit after each of its
five persisted boundaries; recovery and idempotent replay are checked with
fresh repository instances.

Recovery recognizes the exact old or new Thread state. A divergent Thread, hash
mismatch or conflicting Event is reported BLOCKED without overwriting that data.
Unknown JSON fields in an Operation or its plan are also rejected before a
write could discard them; such a record requires explicit review.
Duplicate JSON keys and nonstandard numeric constants are rejected for the
same reason.
The repository also rejects invalid target identities and plan field types on
read and before writing a journal, rather than recording an operation that
cannot be replayed.
Already committed commands replay their original result even after later changes.
This is recoverable multi-file persistence, not an atomic snapshot for readers:
readers can observe a Thread before its Event or commit marker becomes visible.

## Compatibility and limits

The CLI uses `memory/history/operations/thread-status-v1` and
`memory/history/events/thread-status-v1`, plus the analogous `thread-create-v1`
directories, plus `memory/history/operations/thread-delete-v1` for deletion.
The deletion journal has no corresponding business Event.
`ThreadStorage.delete` and the CLI now share
`FilesystemThreadDeletion.for_history`, which wires the canonical creation,
status and deletion journals. Pending creation/status operations block deletion
until recovered (T-039, two local regression cases). The implicit storage path
uses `persistent/../history`; custom history roots or journal layouts require
an explicitly injected complete coordinator. This does not make direct
`ThreadStorage.create/update` coordinated, nor validate manually wired writers.
It never migrates or replays the legacy
CLI journals automatically. Old two-field plans remain readable but cannot be
recovered automatically because their snapshots are missing. Manual migration is
required. The original top-level Event listing does not aggregate these journals.

Only coordinated new repository writers participate in the Thread operation
journals. Legacy writers must not run concurrently against the same Thread
data. Direct low-level Thread writes after a crash can cause a recovery
conflict; they cannot silently be overwritten.

Storage format 0.2 preserves arbitrary Markdown strings. Legacy 0.1 snapshots
remain readable. A new operation still verifies its snapshots round-trip exactly.
This Thread recovery command does not resume Information deletions. New core
deletion requests have a separate `APPLYING_DELETE` receipt and the explicit
`python -m core.information.deletion_recovery --root ROOT --apply` path. Older
ambiguous requests require review; neither command is a boot job yet.

## Rollback

Do not roll back code while operations remain PREPARED/APPLYING. Stop writers,
back up current state, recover or explicitly resolve these records first. Keep
the new journals even if rolling back: older code does not understand their full
recovery guarantees. Never restore an older data archive over later writes without
preserving and reconciling those writes.

## Reprise humaine de FAILED (02/10)

Pour thread-status-v1 et thread-update-v1, `core.operations.failed_resolution` fournit
un aperçu sans écriture puis une décision humaine de reprise du plan inchangé.
La trace d'autorisation et APPLYING sont publiés atomiquement ; la reprise
ordinaire termine ensuite les effets manquants. Le dépôt générique conserve
son refus des sorties FAILED. Voir [contrat et CLI](FAILED-STATUS-RESOLUTION.md).
Les autres familles, abandons et divergences restent à résoudre séparément.
