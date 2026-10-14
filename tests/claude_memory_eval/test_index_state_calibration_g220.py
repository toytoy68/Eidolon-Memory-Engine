# ==========================================================
# Projet      : Eidolon Memory Engine
# Organisation: Eidolon Core Technologies (ECT)
# Fichier     : tests/claude_memory_eval/test_index_state_calibration_g220.py
# Description : Claude G220-6 : jeu de calibration v2 figé et états INDEX_PENDING / STALE / UNAVAILABLE
# Standard    : Eidolon Presentation Standard v1
# ==========================================================
"""Guards the calibration set (not the engine's quality) and pins the index health states produced by the real
read-only chain: journal -> preview -> prepare_work -> summarize_work. Synthetic data only."""
import hashlib
import json
import unicodedata
from pathlib import Path

import pytest

from core.indexing.change_journal import ChangeJournal
from core.indexing.reconcile_plan import Canonical
from core.indexing.reconcile_preview import preview_reconciliation
from core.indexing.worker_prepare import prepare_work
from core.indexing.worker_status import summarize_work

EVAL = Path(__file__).resolve().parents[2] / "docs" / "claude-memory-eval"
DEV2_SHA256 = "ba7446a44d89f4fda5af3d1de6a0156ddace3cbf1b0a7ece84daf163cb043c15"
A = hashlib.sha256(b"a").hexdigest()


def _norm(text):
    text = unicodedata.normalize("NFC", text).casefold()
    return " ".join("".join(c if c.isalnum() else " " for c in text).split())


def test_calibration_v2_is_frozen_superset_of_v1_and_disjoint_from_the_test_set():
    raw = (EVAL / "dev-calibration-v2.json").read_bytes()
    assert hashlib.sha256(raw).hexdigest() == DEV2_SHA256
    dev2 = json.loads(raw)
    dev1 = json.loads((EVAL / "dev-calibration-v1.json").read_text())
    test = json.loads((EVAL / "corpus-v1.json").read_text())
    assert dev1["questions"] == dev2["questions"][:len(dev1["questions"])]
    assert len(dev2["questions"]) >= 60
    ids = {d["id"] for d in test["documents"]}
    held_out = {_norm(q["question"]) for q in test["questions"]}
    seen = set()
    for q in dev2["questions"]:
        text = _norm(q["question"])
        assert text not in held_out and text not in seen
        seen.add(text)
        assert all(e in ids for e in q["expected"])
        assert (q["category"] in ("off_topic", "near_miss")) == (not q["expected"])
    categories = [q["category"] for q in dev2["questions"]]
    assert categories.count("near_miss") >= 8 and categories.count("off_topic") >= 16


def _status(tmp_path, *, canonical, indexed, begin=(), index_available=True, model_compatible=True, age=1):
    journal = ChangeJournal(tmp_path / "changes.sqlite3")
    for ident, revision in begin:
        journal.published(journal.begin(ident, revision, "UPSERT", A))
    created = max((i.created for i in journal.pending()), default=0)
    preview = preview_reconciliation(journal, canonical, indexed, now=created + age)
    work = prepare_work(preview, allow_upsert=True)
    complete = not ((set(indexed) | {i.information_id for i in journal.pending()}) - set(canonical))
    return summarize_work(work, index_available=index_available, canonical_complete=complete,
                          model_compatible=model_compatible)


def test_a_published_but_unindexed_change_is_index_pending(tmp_path):
    status = _status(tmp_path, canonical={"doc": Canonical(2, A)}, indexed={"doc": 1}, begin=[("doc", 2)])
    assert (status.state, status.candidates) == ("INDEX_PENDING", 1)


def test_an_unread_canonical_document_is_index_stale_never_current(tmp_path):
    status = _status(tmp_path, canonical={}, indexed={"doc": 1})
    assert status.state == "INDEX_STALE"


def test_an_unreachable_index_wins_over_every_other_state(tmp_path):
    status = _status(tmp_path, canonical={}, indexed={"doc": 1}, index_available=False, model_compatible=False)
    assert status.state == "INDEX_UNAVAILABLE"


def test_a_complete_and_indexed_corpus_is_index_current(tmp_path):
    status = _status(tmp_path, canonical={"doc": Canonical(1, A)}, indexed={"doc": 1})
    assert status.state == "INDEX_CURRENT"


@pytest.mark.xfail(strict=True, reason="Claude finding S1 (G220, low): INDEX_STALE only means 'canonical "
                   "snapshot incomplete'. A change left unindexed for a week is still INDEX_PENDING: summarize_work "
                   "has no notion of indexing lag. Expected: the oldest pending age above a calibrated threshold "
                   "(study: 2 x p99 of published->indexed, at least 60 s) escalates to INDEX_STALE.")
def test_a_change_pending_for_a_week_is_index_stale(tmp_path):
    status = _status(tmp_path, canonical={"doc": Canonical(2, A)}, indexed={"doc": 1}, begin=[("doc", 2)],
                     age=7 * 24 * 3600)
    assert status.state == "INDEX_STALE"
