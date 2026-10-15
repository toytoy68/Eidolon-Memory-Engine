# ==========================================================
# Projet      : Eidolon Memory Engine
# Organisation: Eidolon Core Technologies (ECT)
# Fichier     : tests/test_index_lag_range_g251.py
# Description : Host timestamp ranges fail through the documented validation boundary.
# Standard    : Eidolon Presentation Standard v1
# ==========================================================
from types import SimpleNamespace
import pytest
from core.indexing.index_lag import evaluate_lag


@pytest.mark.parametrize('field', ['now', 'threshold_seconds', 'clock_skew_seconds', 'created'])
def test_unrepresentable_host_number_is_a_validation_error(field):
    options = dict(now=1000, threshold_seconds=120, clock_skew_seconds=60,
                   index_available=True, index_compatible=True, canonical_complete=True)
    created = 900
    if field == 'created':
        created = 10 ** 400
    else:
        options[field] = 10 ** 400
    with pytest.raises(ValueError, match='invalid'):
        evaluate_lag([SimpleNamespace(created=created)], **options)
