import pytest
from tools.evaluation.relevance_audit import evaluate


def test_positive_and_negative_are_separate():
    result = evaluate([
        {'id': 'a', 'expected_id': 'alpha', 'returned_ids': ['alpha', 'beta']},
        {'id': 'b', 'expected_id': 'gamma', 'returned_ids': ['beta', 'gamma']},
        {'id': 'unknown', 'expected_id': None, 'returned_ids': ['beta']},
    ])
    assert (result['positive_top1'], result['positive_top5']) == (1, 2)
    assert result['negative_with_candidates'] == 1
    assert result['answerability_validated'] is False
    assert result['score_threshold_calibrated'] is False


def test_empty_negative_is_not_a_positive_success():
    result = evaluate([{'id': 'unknown', 'expected_id': None, 'returned_ids': []}])
    assert result['positive_cases'] == 0
    assert result['negative_with_candidates'] == 0


@pytest.mark.parametrize('cases', [[], [{'id': 'x', 'expected_id': None, 'returned_ids': ['a', 'a']}],
    [{'id': 'x', 'expected_id': 1, 'returned_ids': []}],
    [{'id': 'x', 'expected_id': None, 'returned_ids': []},
     {'id': 'x', 'expected_id': None, 'returned_ids': []}]])
def test_reject_invalid_cases(cases):
    with pytest.raises(ValueError):
        evaluate(cases)
