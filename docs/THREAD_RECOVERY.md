# Recoverable Thread status changes

The filesystem coordinator connects Thread state, immutable Event and Operation
records. It is available through `ThreadService` with an injected coordinator,
and through `python -m core.operations.cli`.

## Commands

```sh
python -m core.operations.cli change-status THREAD_ID VALIDATED --previous-revision 1 --operation-id UNIQUE_OPERATION_ID
python -m core.operations.cli recover
```

A Thread must already exist and pass domain validation. The operation ID is a
caller-supplied idempotency key. Repeating the same command returns its original
result without another revision or Event. Reusing its ID for another command is
rejected. The default Event ID is derived deterministically from the operation ID.

Recovery is explicit: run it before accepting mutations after a process restart.
No daemon or scheduled recovery job is installed. The `recover` command returns a
nonzero exit status if a record needs intervention, while independent records are
still processed. Pending operations block new commands for the same Thread.

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

Recovery recognizes the exact old or new Thread state. A divergent Thread, hash
mismatch or conflicting Event is reported BLOCKED without overwriting that data.
Already committed commands replay their original result even after later changes.
This is recoverable multi-file persistence, not an atomic snapshot for readers:
readers can observe a Thread before its Event or commit marker becomes visible.

## Compatibility and limits

The CLI uses `memory/history/operations/thread-status-v1` and
`memory/history/events/thread-status-v1`. It never migrates or replays the legacy
CLI journals automatically. Old two-field plans remain readable but cannot be
recovered automatically because their snapshots are missing. Manual migration is
required. The original top-level Event listing does not aggregate these journals.

Only coordinated new repository writers participate in locks. Legacy writers
must not run concurrently against the same data. Direct low-level Thread writes
after a crash can cause a recovery conflict; they cannot silently be overwritten.

Arbitrary Markdown round-trip support remains a separate migration task. A new
operation refuses snapshots that cannot round-trip through current Thread storage.
The service does not change the previous deletion protocol or promise multi-file
crash recovery for Information deletion.

## Rollback

Do not roll back code while operations remain PREPARED/APPLYING. Stop writers,
back up current state, recover or explicitly resolve these records first. Keep
the new journals even if rolling back: older code does not understand their full
recovery guarantees. Never restore an older data archive over later writes without
preserving and reconciling those writes.
