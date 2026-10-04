"""Additional corruption, scoped recovery and concurrency guards."""
import json
import multiprocessing
import os
import pytest
from core.sources.store import SourceStore, audit_sources
from core.sources.commitments import directory
from core.operations.readiness import check_readiness
from tests.test_source_ai import setup
from tests.test_source_library import add
from tools.vm_acceptance import hashes


def path(root, record):
    return directory(root) / (record['source_id'] + '.json')


@pytest.mark.parametrize('field,value', [('format_version', True), ('paragraph_count', True),
    ('paragraph_count', 0), ('extractor', None), ('committed_at', '2026-10-04'),
    ('source_id', '0'*64), ('source_sha256', '0'*64), ('text_sha256', 'wrong')])
def test_bad_commitment_blocks_without_repair(tmp_path, field, value):
    store, record, _ = setup(tmp_path)
    file = path(tmp_path, record)
    data = json.loads(file.read_text()); data[field] = value
    file.write_text(json.dumps(data))
    before = hashes(tmp_path)
    assert not check_readiness(tmp_path)['ready']
    with pytest.raises(ValueError):
        store.extract(record['source_id'])
    assert hashes(tmp_path) == before


def test_other_pending_extraction_blocks_recovery(tmp_path):
    store, first, _ = setup(tmp_path)
    second = add(store, b'Second source.', original_name='second.txt')['source']
    store.extract(second['source_id'])
    for record in (first, second):
        (store.directory / record['source_id'] / 'extraction.json').unlink()
    before = hashes(tmp_path)
    with pytest.raises(ValueError, match='readiness'):
        store.extract(first['source_id'])
    assert hashes(tmp_path) == before


def test_impossible_promise_missing_extraction_cannot_resume(tmp_path):
    store, record, _ = setup(tmp_path)
    file = path(tmp_path, record); data = json.loads(file.read_text())
    data['text_sha256'] = '0'*64; file.write_text(json.dumps(data))
    (store.directory / record['source_id'] / 'extraction.json').unlink()
    before = hashes(tmp_path)
    assert 'extraction_commitment_mismatch' in {i['reason'] for i in audit_sources(tmp_path)['issues']}
    with pytest.raises(ValueError, match='readiness'):
        store.extract(record['source_id'])
    assert hashes(tmp_path) == before


@pytest.mark.parametrize('linked', ['directory', 'file'])
def test_symlink_commitment_is_not_followed(tmp_path, linked):
    store, record, _ = setup(tmp_path)
    original = path(tmp_path, record)
    outside = tmp_path/'outside'; outside.mkdir()
    if linked == 'file':
        data = original.read_bytes(); original.unlink()
        target = outside/'record.json'; target.write_bytes(data); original.symlink_to(target)
    else:
        original.unlink(); directory(tmp_path).rmdir(); directory(tmp_path).symlink_to(outside, target_is_directory=True)
    before = hashes(outside)
    assert not check_readiness(tmp_path)['ready']
    with pytest.raises(ValueError):
        store.extract(record['source_id'])
    assert hashes(outside) == before


def _worker(root, identity, mode):
    store = SourceStore(root)
    getattr(store, mode)(identity)


@pytest.mark.parametrize('mode', ['extract', 'commit_extraction'])
def test_concurrent_extract_or_explicit_commit_preserves_one_record(tmp_path, mode):
    if 'fork' not in multiprocessing.get_all_start_methods():
        pytest.skip('requires fork')
    store, record, extraction = setup(tmp_path)
    path(tmp_path, record).unlink()
    if mode == 'extract':
        (store.directory / record['source_id'] / 'extraction.json').unlink()
    children = [multiprocessing.get_context('fork').Process(target=_worker,
                args=(tmp_path, record['source_id'], mode)) for _ in range(4)]
    try:
        for child in children: child.start()
        for child in children:
            child.join(15); assert child.exitcode == 0
    finally:
        for child in children:
            if child.is_alive(): child.terminate()
            if child.pid is not None: child.join(5)
    assert len(list(directory(tmp_path).glob('*.json'))) == 1
    assert store.extraction(record['source_id']) == extraction
    assert check_readiness(tmp_path)['ready']
    before = hashes(tmp_path)
    getattr(store, mode)(record['source_id'])
    assert hashes(tmp_path) == before


def test_legacy_preview_then_explicit_commit_does_not_change_snapshot(tmp_path, capsys):
    from tools.commit_source_extraction import main
    store, record, extraction = setup(tmp_path)
    path(tmp_path, record).unlink()
    before = hashes(tmp_path)
    args = ['--root', str(tmp_path), '--id', record['source_id']]
    assert main(args) == 0 and json.loads(capsys.readouterr().out)['status'] == 'PREVIEW'
    assert hashes(tmp_path) == before
    assert audit_sources(tmp_path)['information'] == [dict(source_id=record['source_id'], reason='uncommitted_extraction')]
    assert main(args + ['--apply']) == 0
    assert json.loads(capsys.readouterr().out)['status'] == 'COMMITTED'
    assert store.extraction(record['source_id']) == extraction
    after = hashes(tmp_path)
    assert main(args + ['--apply']) == 0
    assert json.loads(capsys.readouterr().out)['status'] == 'UNCHANGED'
    assert hashes(tmp_path) == after
    assert audit_sources(tmp_path)['information'] == []


def _die_after_publication(root, identity):
    store = SourceStore(root)
    store._checkpoint = lambda stage: os._exit(9) if stage == 'after_extraction_publication' else None
    store.extract(identity)


def test_real_death_after_complete_publication_replays_without_writes(tmp_path):
    if 'fork' not in multiprocessing.get_all_start_methods():
        pytest.skip('requires fork')
    store, record, _ = setup(tmp_path)
    path(tmp_path, record).unlink()
    (store.directory / record['source_id'] / 'extraction.json').unlink()
    child = multiprocessing.get_context('fork').Process(target=_die_after_publication, args=(tmp_path, record['source_id']))
    try:
        child.start(); child.join(15); assert child.exitcode == 9
    finally:
        if child.is_alive(): child.terminate()
        if child.pid is not None: child.join(5)
    before = hashes(tmp_path)
    assert check_readiness(tmp_path)['ready']
    assert store.extract(record['source_id'])['status'] == 'UNCHANGED'
    assert hashes(tmp_path) == before


def test_orphan_and_unknown_commitment_entries_block(tmp_path):
    store, record, _ = setup(tmp_path)
    original = path(tmp_path, record)
    data = json.loads(original.read_text())
    data.update(source_id='0'*64, source_sha256='0'*64)
    (directory(tmp_path)/('0'*64+'.json')).write_text(json.dumps(data))
    (directory(tmp_path)/'unexpected.txt').write_text('private text')
    before = hashes(tmp_path)
    assert not check_readiness(tmp_path)['ready']
    assert {'extraction_commitment_source_unavailable', 'invalid extraction commitment entry'} <= {i['reason'] for i in audit_sources(tmp_path)['issues']}
    assert 'private text' not in json.dumps(audit_sources(tmp_path))
    assert hashes(tmp_path) == before


def test_commitment_invalidates_only_lock_scoped_readiness_cache(tmp_path):
    from core.operations.read_phase import settled_read_phase
    from core.persistence import exclusive_write
    store, record, _ = setup(tmp_path)
    path(tmp_path, record).unlink()
    with exclusive_write(tmp_path/'memory/persistent'), settled_read_phase(tmp_path):
        assert check_readiness(tmp_path)['information']
        store.commit_extraction(record['source_id'])
        assert check_readiness(tmp_path)['information'] == []
    assert check_readiness(tmp_path)['information'] == []
