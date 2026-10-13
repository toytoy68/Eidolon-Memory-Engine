# ==========================================================
# Projet      : Eidolon Memory Engine
# Organisation: Eidolon Core Technologies (ECT)
# Fichier     : core/indexing/reconcile_plan.py
# Description : Proposition Claude G205-B : plans purs de réconciliation, de clôture, de compactage et de retraite
# Standard    : Eidolon Presentation Standard v1
# ==========================================================
"""PROPOSAL (Claude, G205-B), pure functions only: they read facts and return a plan; they never touch the
journal, the canonical Markdown or Qdrant. GPT's worker would execute a plan after re-reading the canon.

Facts in: pending journal intents (core.indexing.change_journal.ChangeIntent), the canonical state read NOW
(revision and content digest per information id, or absent), the index state (revision per id), and,
for abandonment, the age of each intent. Out: an ordered tuple of Actions with a reason.

Rules (the canon always wins; the journal only accelerates):
- a newer canonical revision closes an older intent as SUPERSEDED;
- an INTENT whose canonical write is visible (same revision, same digest; or absent for DELETE) becomes
  PUBLISHED: the writer crashed after the rename and before published();
- an INTENT whose write is NOT visible is closed ABANDONED only after a grace delay, never before (the
  writer may be between begin() and the rename); without a known age, it WAITs;
- a same revision with another digest is an INTEGRITY alert, never indexed;
- manifest reconciliation: an id whose index revision differs from the canon with no intent covering it
  gets an ENQUEUE action (the journal lost the event); an indexed id absent from the canon is deleted.
"""
from dataclasses import dataclass

TERMINAL = frozenset({"INDEXED", "SUPERSEDED", "ABANDONED"})
ACTIONS = ("MARK_PUBLISHED", "INDEX_UPSERT", "INDEX_DELETE", "CLOSE_SUPERSEDED", "CLOSE_ABANDONED",
           "WAIT", "INTEGRITY_ALERT", "ENQUEUE_UPSERT", "ENQUEUE_DELETE")


@dataclass(frozen=True)
class Canonical:
    revision: int
    sha256: str


@dataclass(frozen=True)
class Action:
    kind: str
    information_id: str
    sequence: int | None
    revision: int | None
    reason: str


def _intent_action(intent, canonical, age, grace_seconds):
    current = canonical.get(intent.information_id)
    seq, ident = intent.sequence, intent.information_id
    if current is not None and current.revision > intent.revision:
        return Action("CLOSE_SUPERSEDED", ident, seq, current.revision, "newer canonical revision")
    if intent.operation == "UPSERT":
        visible = current is not None and current.revision == intent.revision
        if visible and current.sha256 != intent.canonical_sha256:
            return Action("INTEGRITY_ALERT", ident, seq, intent.revision, "same revision, other content")
    else:
        visible = current is None
    if intent.state == "INTENT":
        if visible:
            return Action("MARK_PUBLISHED", ident, seq, intent.revision, "canonical write is visible")
        if age is not None and age > grace_seconds:
            return Action("CLOSE_ABANDONED", ident, seq, intent.revision, "canonical write never visible")
        return Action("WAIT", ident, seq, intent.revision, "write may still be in flight")
    if intent.state == "PUBLISHED":
        if not visible:
            return Action("INTEGRITY_ALERT", ident, seq, intent.revision, "published write no longer visible")
        kind = "INDEX_UPSERT" if intent.operation == "UPSERT" else "INDEX_DELETE"
        return Action(kind, ident, seq, intent.revision, "published, not yet indexed")
    raise ValueError("terminal intents are not pending")


def reconcile_plan(pending, canonical, indexed, *, ages=None, grace_seconds=600):
    """pending: ChangeIntent tuple; canonical: {id: Canonical}; indexed: {id: revision}; ages: {seq: s}."""
    if type(grace_seconds) not in (int, float) or grace_seconds < 0:
        raise ValueError("invalid grace delay")
    ages = ages or {}
    actions, covered = [], set()
    for intent in sorted(pending, key=lambda i: i.sequence):
        if intent.state in TERMINAL:
            raise ValueError("terminal intents are not pending")
        action = _intent_action(intent, canonical, ages.get(intent.sequence), grace_seconds)
        actions.append(action)
        if action.kind not in ("CLOSE_SUPERSEDED", "CLOSE_ABANDONED"):
            covered.add(intent.information_id)
    for ident in sorted(set(canonical) | set(indexed)):
        if ident in covered:
            continue
        current, revision = canonical.get(ident), indexed.get(ident)
        if current is None:
            actions.append(Action("ENQUEUE_DELETE", ident, None, revision, "indexed but absent from the canon"))
        elif revision != current.revision:
            actions.append(Action("ENQUEUE_UPSERT", ident, None, current.revision,
                                  "index revision differs and no intent covers it"))
    return tuple(actions)


def compaction_plan(rows, *, oldest_active_reader_sequence, keep_last=1000):
    """Sequences that may be deleted: TERMINAL rows below every active reader's floor, keeping the newest
    ``keep_last`` terminal rows for audit. Never a pending row. rows: iterable of (sequence, state)."""
    if type(keep_last) is not int or keep_last < 0:
        raise ValueError("invalid keep_last")
    if oldest_active_reader_sequence is not None and type(oldest_active_reader_sequence) is not int:
        raise ValueError("invalid reader floor")
    terminal = sorted(seq for seq, state in rows if state in TERMINAL)
    candidates = terminal[:max(0, len(terminal) - keep_last)]
    floor = oldest_active_reader_sequence
    return tuple(seq for seq in candidates if floor is None or seq < floor)


def retirement_plan(generations, *, live, readers, retired_at, now, grace_seconds=3600):
    """Generations (collection names) that may be dropped: never the live alias target, never one with an
    active reader, only after a grace delay since it stopped being live. Unknown history = keep."""
    if live not in generations:
        raise ValueError("live generation unknown: refuse to plan anything")
    out = []
    for name in sorted(generations):
        if name == live or readers.get(name, 0) != 0:
            continue
        since = retired_at.get(name)
        if since is not None and now - since >= grace_seconds:
            out.append(name)
    return tuple(out)
