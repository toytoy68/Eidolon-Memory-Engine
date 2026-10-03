"""A cooperative publication in flight must not be diagnosed as a blocked destination."""
import os
import threading

import pytest

import core.migration.deleted_receipts as module
from core.migration.deleted_receipts import import_deleted_receipts
from core.operations.readiness import check_readiness
from core.persistence import exclusive_write
from tests.test_deleted_receipt_import import seed
from tests.test_migration_converter import fingerprints


class PausedRename:
    """Hold the first durable rename after its temporary file exists."""

    def __init__(self, monkeypatch):
        self.reached, self.release, self.real = threading.Event(), threading.Event(), os.replace
        self.used = False
        monkeypatch.setattr(os, 'replace', self)

    def __call__(self, source, destination):
        if not self.used and 'pending-delete' in str(destination):
            self.used = True
            self.reached.set()
            assert self.release.wait(20)
        return self.real(source, destination)


def run(results, key, source, destination):
    results[key] = import_deleted_receipts(source, destination)


def test_importer_arriving_during_publication_waits_then_converges(tmp_path, monkeypatch):
    source, destination, src, dst = seed(tmp_path)
    pause, results = PausedRename(monkeypatch), {}
    first = threading.Thread(target=run, args=(results, 'first', source, destination))
    first.start()
    assert pause.reached.wait(10)
    # The first importer's temporary is visible: an unlocked audit reports the tree blocked.
    assert not check_readiness(destination)['ready']
    second = threading.Thread(target=run, args=(results, 'second', source, destination))
    second.start()
    second.join(1)
    waited = second.is_alive()
    pause.release.set()
    first.join(10)
    second.join(10)
    assert waited, results.get('second')  # waits for the locks instead of concluding
    assert results['first']['status'] == 'IMPORTED' and results['first']['imported'] == ['deleted-0', 'deleted-1']
    assert results['second']['status'] == 'UNCHANGED' and results['second']['imported'] == []
    assert check_readiness(destination)['ready']
    for identity in ('deleted-0', 'deleted-1'):
        assert (dst.pending_delete_root / (identity + '.json')).read_bytes() == (
            src.pending_delete_root / (identity + '.json')).read_bytes()


def test_destination_still_blocked_under_locks_stays_blocked_without_publication(tmp_path):
    source, destination, _, dst = seed(tmp_path)
    with exclusive_write(dst.persistent_root):
        pass  # a cooperative writer has already used this destination
    dst.pending_delete_root.mkdir(parents=True, exist_ok=True)
    (dst.pending_delete_root / '.deleted-0.json.abandoned').write_text('{')
    before = fingerprints(source), fingerprints(destination)
    result = import_deleted_receipts(source, destination)
    assert result['status'] == 'BLOCKED' and result['imported'] == []
    assert result['issues'][0]['side'] == 'destination'
    assert (fingerprints(source), fingerprints(destination)) == before


def test_blocked_destination_never_locked_creates_no_lock_file(tmp_path):
    source, destination, _, dst = seed(tmp_path)
    dst.pending_delete_root.mkdir(parents=True, exist_ok=True)
    (dst.pending_delete_root / '.deleted-0.json.abandoned').write_text('{')
    assert not (dst.persistent_root / '.write.lock').exists()
    before = fingerprints(destination)
    assert import_deleted_receipts(source, destination)['status'] == 'BLOCKED'
    assert fingerprints(destination) == before


@pytest.mark.parametrize('fault', ['source_readiness', 'receipt_conflict', 'overlap'])
def test_non_contention_issues_stay_immediate_without_taking_destination_locks(tmp_path, fault):
    source, destination, src, dst = seed(tmp_path)
    if fault == 'source_readiness':
        (src.pending_delete_root / '.deleted-0.json.abandoned').write_text('{')
    elif fault == 'receipt_conflict':
        dst.pending_delete_root.mkdir(parents=True, exist_ok=True)
        (dst.pending_delete_root / 'deleted-0.json').write_bytes(
            (src.pending_delete_root / 'deleted-0.json').read_bytes().replace(b'delete-0', b'delete-X'))
    results, holding, release = {}, threading.Event(), threading.Event()

    def hold():
        with exclusive_write(dst.persistent_root):
            holding.set()
            release.wait(20)
    holder = threading.Thread(target=hold)
    holder.start()
    assert holding.wait(5)
    try:
        target = source if fault == 'overlap' else destination
        worker = threading.Thread(target=run, args=(results, 'only', source, target))
        worker.start()
        worker.join(5)
        assert not worker.is_alive(), 'import waited for the destination lock'
    finally:
        release.set()
        holder.join(5)
    assert results['only']['status'] == 'BLOCKED' and results['only']['imported'] == []


def test_include_cancelled_importer_also_waits_for_cooperative_publication(tmp_path, monkeypatch):
    source, destination, _, _ = seed(tmp_path)
    pause, results = PausedRename(monkeypatch), {}
    first = threading.Thread(target=run, args=(results, 'first', source, destination))
    first.start()
    assert pause.reached.wait(10)
    second = threading.Thread(target=lambda: results.setdefault(
        'second', import_deleted_receipts(source, destination, include_cancelled=True)))
    second.start()
    second.join(1)
    waited = second.is_alive()
    pause.release.set()
    first.join(10)
    second.join(10)
    assert waited and sorted(r['status'] for r in results.values()) == ['IMPORTED', 'UNCHANGED']


def test_contended_precheck_never_publishes_a_prefix_when_the_locked_audit_finds_a_conflict(tmp_path, monkeypatch):
    source, destination, src, dst = seed(tmp_path)
    with exclusive_write(dst.persistent_root):
        pass
    dst.pending_delete_root.mkdir(parents=True, exist_ok=True)
    (dst.pending_delete_root / 'deleted-1.json').write_bytes(
        (src.pending_delete_root / 'deleted-1.json').read_bytes().replace(b'delete-1', b'delete-X'))
    real, calls = module.check_readiness, []
    def transient(root):
        calls.append(str(root))
        if len(calls) == 2:  # first destination audit, before the locks
            return {'ready': False, 'issues': [{'path': 'memory/history/pending-delete/.x', 'reason': 'unknown_history_file', 'resumable': False}]}
        return real(root)
    monkeypatch.setattr(module, 'check_readiness', transient)
    before = fingerprints(destination)
    result = import_deleted_receipts(source, destination)
    assert result['status'] == 'BLOCKED' and result['imported'] == []
    assert fingerprints(destination) == before
    assert not (dst.pending_delete_root / 'deleted-0.json').exists()
