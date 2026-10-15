# ==========================================================
# Projet      : Eidolon Memory Engine
# Organisation: Eidolon Core Technologies (ECT)
# Fichier     : tests/test_index_lag_unknown_g250.py
# Description : Unknown intent ages never produce a claimed global oldest age.
# Standard    : Eidolon Presentation Standard v1
# ==========================================================
from types import SimpleNamespace

from core.indexing.index_lag import evaluate_lag


def test_unknown_age_keeps_known_lag_evidence_without_claiming_oldest():
    result = evaluate_lag([SimpleNamespace(created=None), SimpleNamespace(created=500)],
        now=1000, threshold_seconds=120, index_available=True, index_compatible=True,
        canonical_complete=True)
    assert result.state == 'INDEX_LAGGING'
    assert result.lagging == 1  # known lower bound, not a total for unknown timestamps
    assert result.oldest_age_seconds is None
    assert 'AGE_UNKNOWN' in result.reasons


def test_unknown_age_does_not_make_a_recent_known_age_the_global_oldest():
    result = evaluate_lag([SimpleNamespace(created=990), SimpleNamespace(created=None)],
        now=1000, threshold_seconds=120, index_available=True, index_compatible=True,
        canonical_complete=True)
    assert result.state == 'INDEX_PENDING' and result.lagging == 0
    assert result.oldest_age_seconds is None
    assert result.reasons == ('AGE_UNKNOWN',)
