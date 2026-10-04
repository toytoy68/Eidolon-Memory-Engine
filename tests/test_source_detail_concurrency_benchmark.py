"""Concurrent measurement checks both convergence and distinct reviewed details."""
import multiprocessing
import pytest
from tools.benchmark_source_detail_concurrency import run

pytestmark = pytest.mark.skipif('fork' not in multiprocessing.get_all_start_methods(), reason='fork required')


def test_concurrent_benchmark_checks_identity_counts_and_integrity(tmp_path):
    report = run(sizes=(2,), workers=3, replicas=1, temp_parent=tmp_path)
    assert report['status'] == 'PASS'
    shared, distinct = report['points']
    assert shared['new_objects'] == 1 and distinct['new_objects'] == 3
    for point in (shared, distinct):
        assert point['protected_files_unchanged'] and point['readiness']
        assert point['audit_issues'] == 0 and len(point['worker_seconds']) == 3
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize('workers', [1, 9, True])
def test_unsafe_worker_counts_do_not_create_corpus(tmp_path, workers):
    with pytest.raises(ValueError):
        run(sizes=(0,), replicas=1, workers=workers, temp_parent=tmp_path)
    assert list(tmp_path.iterdir()) == []
