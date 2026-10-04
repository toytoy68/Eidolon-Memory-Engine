"""Benchmark validates canonical state and measures the compatibility scan."""
import pytest
from tools.benchmark_source_details import run


def test_fresh_corpora_scan_new_details_but_replay_is_unchanged(tmp_path):
    report = run(sizes=(0, 3), replicas=2, temp_parent=tmp_path)
    assert report['status'] == 'PASS' and len(report['points']) == 8
    for point in report['points']:
        assert point['audit_issues'] == 0 and point['readiness']
        assert point['canonical_objects'] == point['history_records']+1
        if point['history_records']:
            assert point['journal_json_opens'] > 0
        if point['mode'] == 'new':
            assert point['backend_list_calls'] == 1
            assert point['backend_list_items'] == point['history_records']
            assert not point['files_unchanged']
        else:
            assert point['backend_list_calls'] == 0
            assert point['files_unchanged']
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize('sizes,replicas', [([], 1), ([-1], 1), ([True], 1), ([0], 0)])
def test_invalid_measurement_does_not_create_corpus(tmp_path, sizes, replicas):
    with pytest.raises(ValueError):
        run(sizes=sizes, replicas=replicas, temp_parent=tmp_path)
    assert list(tmp_path.iterdir()) == []
