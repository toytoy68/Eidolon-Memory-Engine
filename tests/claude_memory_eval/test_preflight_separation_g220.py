# ==========================================================
# Projet      : Eidolon Memory Engine
# Organisation: Eidolon Core Technologies (ECT)
# Fichier     : tests/claude_memory_eval/test_preflight_separation_g220.py
# Description : Contre-revue Claude G220-2 : séparation attente / revue / refus (preflight, prepare, preview)
# Standard    : Eidolon Presentation Standard v1
# ==========================================================
"""Pins GPT's G220 decision: an ordinary WAIT is not a human review; integrity, abandonment and supersession
are. Built from real journal rows through the preview, then preflight and prepare_work."""
import hashlib

from core.indexing.change_journal import ChangeJournal
from core.indexing.reconcile_plan import ABSENT, Canonical
from core.indexing.reconcile_preview import preview_reconciliation
from core.indexing.worker_preflight import preflight
from core.indexing.worker_prepare import prepare_work

A = hashlib.sha256(b"a").hexdigest()


def journal(tmp_path):
    return ChangeJournal(tmp_path / "changes.sqlite3")


def test_an_in_flight_write_is_waiting_never_review_never_candidate(tmp_path):
    j = journal(tmp_path)
    j.begin("doc", 2, "UPSERT", A)
    created = j.pending()[0].created
    preview = preview_reconciliation(j, {"doc": Canonical(1, A)}, {"doc": 1}, now=created + 5)
    assert [a.kind for a in preview.actions] == ["WAIT"] and not preview.requires_review
    work = prepare_work(preview, allow_upsert=True)
    assert (work.candidate_ids, work.review_ids, work.waiting_ids) == ((), (), ("doc",))


def test_review_items_block_every_candidate_of_the_same_preview(tmp_path):
    """Conservative by design: one supersession in a preview withholds all upserts of that preview."""
    j = journal(tmp_path)
    j.published(j.begin("old", 1, "UPSERT", A))
    created = j.pending()[0].created
    preview = preview_reconciliation(j, {"old": Canonical(3, A), "new": Canonical(1, A)}, {"old": 1},
                                     now=created + 1)
    assert preview.requires_review
    work = prepare_work(preview, allow_upsert=True)
    assert work.candidate_ids == () and "old" in work.review_ids and "new" in work.blocked_ids


def test_upserts_are_refused_unless_explicitly_allowed_and_deletes_are_always_review(tmp_path):
    j = journal(tmp_path)
    preview = preview_reconciliation(j, {"new": Canonical(1, A), "gone": ABSENT}, {"gone": 4})
    denied, allowed = preflight(preview.actions), preflight(preview.actions, allow_upsert=True)
    assert [a.kind for a in denied.refused] == ["ENQUEUE_UPSERT"] and denied.proposals == ()
    assert [a.kind for a in allowed.proposals] == ["ENQUEUE_UPSERT"]
    assert [a.kind for a in allowed.review] == ["ENQUEUE_DELETE"]


def test_journal_recovery_is_never_an_executable_index_proposal(tmp_path):
    j = journal(tmp_path)
    j.begin("doc", 1, "UPSERT", A)
    preview = preview_reconciliation(j, {"doc": Canonical(1, A)}, {})
    result = preflight(preview.actions, allow_upsert=True)
    assert [a.kind for a in result.review] == ["MARK_PUBLISHED"] and result.proposals == ()
