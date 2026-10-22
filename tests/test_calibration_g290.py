import pytest
from tools.evaluation.calibration import exploratory_separation


def test_exploratory_separation_never_approves_deployment():
    x = exploratory_separation([
        {'expected_id': 'a', 'returned_ids': ['a'], 'first_score': .6},
        {'expected_id': None, 'returned_ids': ['b'], 'first_score': .2}])
    assert x['sample_separated'] and x['sample_midpoint'] == .4
    assert not x['deployment_approved'] and not x['independent_validation']


def test_overlap_is_not_hidden():
    x = exploratory_separation([
        {'expected_id': 'a', 'returned_ids': ['a'], 'first_score': .3},
        {'expected_id': None, 'returned_ids': ['b'], 'first_score': .5}])
    assert not x['sample_separated'] and x['sample_midpoint'] is None


@pytest.mark.parametrize('cases', [[],
    [{'expected_id': None, 'returned_ids': ['a'], 'first_score': .1}],
    [{'expected_id': 'a', 'returned_ids': ['b'], 'first_score': .6},
     {'expected_id': None, 'returned_ids': ['b'], 'first_score': .2}],
    [{'expected_id': 'a', 'returned_ids': ['a'], 'first_score': float('nan')},
     {'expected_id': None, 'returned_ids': ['b'], 'first_score': .2}]])
def test_reject_bad_calibration(cases):
    with pytest.raises(ValueError): exploratory_separation(cases)
