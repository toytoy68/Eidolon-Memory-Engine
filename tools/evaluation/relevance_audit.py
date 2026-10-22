# Eidolon Core Technologies — observational relevance audit; no production gating.
"""Evaluate externally supplied recall evidence without asserting answerability.

Input: JSON object with cases [{id, expected_id (or null), returned_ids}].
This is an *identity retrieval* metric only, never a truth/relevance threshold.
No network, model or canonical storage is touched.
"""
import argparse
import json
from pathlib import Path


def evaluate(cases):
    if not isinstance(cases, list) or not cases:
        raise ValueError('nonempty cases required')
    seen = set()
    details = []
    for case in cases:
        if not isinstance(case, dict) or set(case) != {'id', 'expected_id', 'returned_ids'}:
            raise ValueError('invalid case schema')
        ident, expected, returned = case['id'], case['expected_id'], case['returned_ids']
        if not isinstance(ident, str) or not ident or ident in seen:
            raise ValueError('duplicate/invalid case id')
        seen.add(ident)
        if expected is not None and (not isinstance(expected, str) or not expected):
            raise ValueError('invalid expected identity')
        if (not isinstance(returned, list) or len(returned) > 100 or
                any(not isinstance(x, str) or not x for x in returned) or
                len(returned) != len(set(returned))):
            raise ValueError('invalid returned identities')
        rank = returned.index(expected)+1 if expected in returned else None
        details.append({'id': ident, 'kind': 'negative' if expected is None else 'positive',
                        'expected_rank': rank, 'candidates_returned': len(returned),
                        'negative_with_candidates': expected is None and bool(returned)})
    positives = [x for x in details if x['kind'] == 'positive']
    negatives = [x for x in details if x['kind'] == 'negative']
    return {'schema': 'eidolon-relevance-audit/1', 'cases': len(details),
            'positive_cases': len(positives), 'negative_cases': len(negatives),
            'positive_top1': sum(x['expected_rank'] == 1 for x in positives),
            'positive_top5': sum(x['expected_rank'] is not None and x['expected_rank'] <= 5 for x in positives),
            'negative_with_candidates': sum(x['negative_with_candidates'] for x in negatives),
            'answerability_validated': False, 'score_threshold_calibrated': False,
            'details': details}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', required=True, type=Path)
    args = parser.parse_args()
    payload = json.loads(args.input.read_text(encoding='utf-8'))
    if not isinstance(payload, dict) or set(payload) != {'cases'}:
        parser.error('invalid input')
    print(json.dumps(evaluate(payload['cases']), sort_keys=True))


if __name__ == '__main__':
    main()
