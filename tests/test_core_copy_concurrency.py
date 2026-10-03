"""A cooperative copy in flight must not be reported as a blocked destination."""
import os
import threading

import core.migration.core_copy as module
from core.migration.core_copy import copy_core, inspect_core_copy
from core.persistence import exclusive_write
from tests.test_core_copy import seed
from tests.test_migration_converter import fingerprints


def test_copier_arriving_during_staging_waits_then_reports_unchanged(tmp_path, monkeypatch):
    source, destination, *_ = seed(tmp_path)
    reached, release, results, real = threading.Event(), threading.Event(), {}, os.replace
    state = {'used': False}

    def paused(src, dst):
        if not state['used'] and '.core-copy-v1' in str(dst):
            state['used'] = True
            reached.set()
            assert release.wait(20)
        return real(src, dst)
    monkeypatch.setattr(os, 'replace', paused)
    first = threading.Thread(target=lambda: results.setdefault('first', copy_core(source, destination)))
    first.start()
    assert reached.wait(10)
    assert inspect_core_copy(source, destination)['status'] == 'BLOCKED'  # staging visible, unlocked
    second = threading.Thread(target=lambda: results.setdefault('second', copy_core(source, destination)))
    second.start()
    second.join(1)
    waited = second.is_alive()
    release.set()
    first.join(20)
    second.join(20)
    assert waited, results.get('second')
    assert results['first']['status'] == 'COPIED' and results['second']['status'] == 'UNCHANGED'


def test_abandoned_invalid_staging_stays_blocked_without_writes(tmp_path):
    source, destination, *_ = seed(tmp_path)
    with exclusive_write(destination.parent):
        pass
    stage = destination.parent / ('.' + destination.name + '.core-copy-v1')
    stage.mkdir()
    (stage / 'unknown').write_text('x')
    before = fingerprints(tmp_path)
    assert copy_core(source, destination)['status'] == 'BLOCKED'
    assert fingerprints(tmp_path) == before and not destination.exists()


def test_blocked_source_does_not_wait_for_the_destination_lock(tmp_path):
    source, destination, *_ = seed(tmp_path)
    (source / 'memory/history/operations').mkdir(parents=True, exist_ok=True)
    (source / 'memory/history/operations/unknown-v1').mkdir()
    (source / 'memory/history/operations/unknown-v1/pending.json').write_text('{}')
    holding, release, results = threading.Event(), threading.Event(), {}

    def hold():
        with exclusive_write(destination.parent):
            holding.set()
            release.wait(20)
    holder = threading.Thread(target=hold)
    holder.start()
    assert holding.wait(5)
    try:
        worker = threading.Thread(target=lambda: results.setdefault('only', copy_core(source, destination)))
        worker.start()
        worker.join(10)
        assert not worker.is_alive(), 'copy waited for the destination lock'
    finally:
        release.set()
        holder.join(5)
    assert results['only']['status'] == 'BLOCKED' and not destination.exists()
