# Eidolon Core Technologies — experimental calibration, never a production gate.
"""Explore separation of labeled positive and negative recall scores.

A threshold found on this same sample is exploratory only; independent holdout
validation and per-model/version provenance are required before use in Core.
"""
from math import isfinite


def exploratory_separation(cases):
    if not isinstance(cases, list) or len(cases) < 2:
        raise ValueError('at least two cases required')
    positives, negatives = [], []
    for case in cases:
        if not isinstance(case, dict) or set(case) != {'expected_id', 'returned_ids', 'first_score'}:
            raise ValueError('invalid case')
        expected, returned, score = case['expected_id'], case['returned_ids'], case['first_score']
        if not isinstance(returned, list) or not returned or not all(isinstance(x, str) for x in returned):
            raise ValueError('invalid returned identities')
        if type(score) not in (float, int) or not isfinite(score):
            raise ValueError('invalid score')
        if expected is None:
            negatives.append(score)
        elif isinstance(expected, str) and expected and returned[0] == expected:
            positives.append(score)
        else:
            raise ValueError('positive case must have expected top1 identity')
    if not positives or not negatives:
        raise ValueError('positive and negative labels required')
    low, high = min(positives), max(negatives)
    return {'schema': 'eidolon-calibration-exploration/1', 'positive_count': len(positives),
            'negative_count': len(negatives), 'positive_min': low, 'negative_max': high,
            'sample_separated': low > high,
            'sample_midpoint': (low+high)/2 if low > high else None,
            'deployment_approved': False, 'independent_validation': False,
            'score_is_proof': False}
