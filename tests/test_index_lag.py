# ==========================================================
# Projet      : Eidolon Memory Engine
# Organisation: Eidolon Core Technologies (ECT)
# Fichier     : tests/test_index_lag.py
# Description : Tests de l'évaluateur pur de retard d'indexation (Claude, G236-6)
# Standard    : Eidolon Presentation Standard v1
# ==========================================================
import hashlib

import pytest

from core.indexing.change_journal import ChangeJournal
from core.indexing.index_lag import evaluate_lag
from core.indexing.reconcile_plan import Canonical
from core.indexing.reconcile_preview import preview_reconciliation
from core.indexing.worker_prepare import prepare_work
from core.indexing.worker_status import summarize_work


class Intent:
    def __init__(self, created):
        self.created = created


HEALTHY = dict(index_available=True, index_compatible=True, canonical_complete=True)


def lag(pending, now=1000.0, threshold=120, **flags):
    return evaluate_lag(pending, now=now, threshold_seconds=threshold, **{**HEALTHY, **flags})


def test_current_pending_and_lagging_are_distinct():
    assert lag([]).state == "INDEX_CURRENT"
    assert lag([Intent(950)]).state == "INDEX_PENDING"
    report = lag([Intent(950), Intent(500)])
    assert (report.state, report.lagging, report.oldest_age_seconds) == ("INDEX_LAGGING", 1, 500.0)


def test_exact_threshold_is_not_lagging():
    assert lag([Intent(880)]).state == "INDEX_PENDING"          # 120 s == threshold
    assert lag([Intent(879)]).state == "INDEX_LAGGING"


def test_health_and_canonical_coverage_win_but_ageing_stays_visible():
    old = [Intent(0)]
    assert lag(old, index_available=False).state == "INDEX_UNAVAILABLE"
    assert lag(old, index_compatible=False).state == "INDEX_INCOMPATIBLE"
    report = lag(old, canonical_complete=False)
    assert report.state == "CANONICAL_INCOMPLETE" and "ALSO_LAGGING" in report.reasons
    assert lag([], canonical_complete=False).state == "CANONICAL_INCOMPLETE"


def test_unknown_or_future_dates_never_produce_an_ageing_verdict():
    unknown = lag([Intent(None)])
    assert unknown.state == "INDEX_PENDING" and unknown.reasons == ("AGE_UNKNOWN",)
    ahead = lag([Intent(5000), Intent(0)])
    assert ahead.reasons == ("CLOCK_AHEAD",) and ahead.oldest_age_seconds is None and ahead.lagging == 0
    assert lag([Intent(1050)]).state == "INDEX_PENDING"          # within 60 s of skew


@pytest.mark.parametrize("bad", [dict(threshold=0), dict(threshold=-1), dict(threshold=float("inf")),
                                 dict(threshold=True), dict(threshold="60"), dict(now=float("nan")),
                                 dict(index_available=1)])
def test_the_threshold_is_mandatory_and_inputs_are_checked(bad):
    with pytest.raises(ValueError):
        lag([Intent(950)], **bad)
    with pytest.raises(TypeError):
        evaluate_lag([], now=1.0, **HEALTHY)                       # no default threshold


def test_works_on_real_journal_rows_and_complements_worker_status(tmp_path):
    """The S1 case: a change unindexed for a week. worker_status says PENDING; the lag evaluator says LAGGING."""
    journal = ChangeJournal(tmp_path / "changes.sqlite3")
    digest = hashlib.sha256(b"a").hexdigest()
    journal.published(journal.begin("doc", 2, "UPSERT", digest))
    created = journal.pending()[0].created
    week = created + 7 * 24 * 3600
    preview = preview_reconciliation(journal, {"doc": Canonical(2, digest)}, {"doc": 1}, now=week)
    status = summarize_work(prepare_work(preview, allow_upsert=True), index_available=True,
                            canonical_complete=True, model_compatible=True)
    report = evaluate_lag(journal.pending(), now=week, threshold_seconds=3600, **HEALTHY)
    assert (status.state, report.state) == ("INDEX_PENDING", "INDEX_LAGGING")
