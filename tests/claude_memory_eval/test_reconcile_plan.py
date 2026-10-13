# ==========================================================
# Projet      : Eidolon Memory Engine
# Organisation: Eidolon Core Technologies (ECT)
# Fichier     : tests/claude_memory_eval/test_reconcile_plan.py
# Description : Tests de la proposition Claude G205-B : clôture, réconciliation, compactage, retraite
# Standard    : Eidolon Presentation Standard v1
# ==========================================================
import hashlib

import pytest

from core.indexing.change_journal import ChangeIntent, ChangeJournal
from core.indexing.reconcile_plan import ABSENT, Canonical, compaction_plan, reconcile_plan, retirement_plan

A = hashlib.sha256(b"a").hexdigest()
B = hashlib.sha256(b"b").hexdigest()


def intent(seq, ident, rev, op="UPSERT", sha=A, state="INTENT"):
    return ChangeIntent(seq, ident, rev, op, sha if op == "UPSERT" else None, state)


def kinds(plan):
    return [(a.kind, a.information_id) for a in plan]


def test_crash_after_rename_is_recovered_as_published_once():
    plan = reconcile_plan([intent(1, "doc", 2)], {"doc": Canonical(2, A)}, {"doc": 1})
    assert kinds(plan) == [("MARK_PUBLISHED", "doc")]


def test_unvisible_write_waits_then_is_abandoned_only_after_grace():
    pending = [intent(1, "doc", 3)]
    canon = {"doc": Canonical(2, A)}
    assert kinds(reconcile_plan(pending, canon, {"doc": 2})) == [("WAIT", "doc")]               # age unknown
    assert kinds(reconcile_plan(pending, canon, {"doc": 2}, ages={1: 30})) == [("WAIT", "doc")]
    assert kinds(reconcile_plan(pending, canon, {"doc": 2}, ages={1: 601})) == [("CLOSE_ABANDONED", "doc")]


def test_newer_canon_supersedes_and_still_gets_indexed():
    plan = reconcile_plan([intent(1, "doc", 2, state="PUBLISHED")], {"doc": Canonical(4, B)}, {"doc": 2})
    assert kinds(plan) == [("CLOSE_SUPERSEDED", "doc"), ("ENQUEUE_UPSERT", "doc")]
    assert plan[1].revision == 4


def test_same_revision_other_content_is_an_alert_never_indexed():
    plan = reconcile_plan([intent(1, "doc", 2, state="PUBLISHED")], {"doc": Canonical(2, B)}, {})
    assert kinds(plan) == [("INTEGRITY_ALERT", "doc")]


def test_deletes_and_lost_events_are_reconciled_from_the_manifest():
    plan = reconcile_plan([intent(1, "gone", 3, op="DELETE")], {"new": Canonical(1, A), "gone": ABSENT, "orphan": ABSENT},
                          {"gone": 3, "orphan": 5})
    assert kinds(plan) == [("MARK_PUBLISHED", "gone"), ("ENQUEUE_UPSERT", "new"), ("ENQUEUE_DELETE", "orphan")]
    published = reconcile_plan([intent(1, "gone", 3, op="DELETE", state="PUBLISHED")], {"gone": ABSENT}, {"gone": 3})
    assert kinds(published) == [("INDEX_DELETE", "gone")]


def test_works_on_real_journal_rows(tmp_path):
    journal = ChangeJournal(tmp_path / "changes.sqlite3")
    seq = journal.begin("doc", 1, "UPSERT", A)
    plan = reconcile_plan(journal.pending(), {"doc": Canonical(1, A)}, {})
    assert [(a.kind, a.sequence) for a in plan] == [("MARK_PUBLISHED", seq)]


def test_compaction_never_touches_pending_rows_or_rows_a_reader_may_need():
    rows = [(1, "INDEXED"), (2, "SUPERSEDED"), (3, "INTENT"), (4, "ABANDONED"), (5, "INDEXED"), (6, "PUBLISHED")]
    assert compaction_plan(rows, oldest_active_reader_sequence=None, keep_last=0) == (1, 2, 4, 5)
    assert compaction_plan(rows, oldest_active_reader_sequence=4, keep_last=0) == (1, 2)
    assert compaction_plan(rows, oldest_active_reader_sequence=None, keep_last=2) == (1, 2)


def test_retirement_spares_live_read_and_recent_generations():
    generations = {"g1", "g2", "g3", "g4"}
    plan = retirement_plan(generations, live="g4", readers={"g1": 0, "g2": 1, "g3": 0}, retired_at={"g1": 0, "g2": 0, "g3": 3000},
                           now=4000, grace_seconds=3600)
    assert plan == ("g1",)                       # g2 is being read, g3 too recent, g4 live
    assert retirement_plan(generations, live="g4", readers={}, retired_at={}, now=10**9) == ()  # unknown history
    with pytest.raises(ValueError):
        retirement_plan({"g1"}, live="g9", readers={}, retired_at={"g1": 0}, now=10**9)

def test_unknown_canonical_does_not_trigger_deletion():
    plan = reconcile_plan([intent(1, "doc", 3, op="DELETE")], {}, {"doc": 3}, ages={1: 99999})
    assert kinds(plan) == [("WAIT", "doc")]
    for bad in (None, 3, "absent"):
        with pytest.raises(ValueError):
            reconcile_plan([intent(1, "doc", 3, op="DELETE")], {"doc": bad}, {"doc": 3})


def test_unknown_readers_prevent_generation_retirement():
    assert retirement_plan({"g1", "g2"}, live="g2", readers={}, retired_at={"g1": 0}, now=99999) == ()
