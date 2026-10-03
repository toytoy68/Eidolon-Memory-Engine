"""Original sources are exact immutable artifacts, never ingested as memories."""
from hashlib import sha256
from pathlib import Path
import multiprocessing
import os

import pytest

from core.backend.filesystem import FilesystemBackend
from core.migration.core_copy import copy_core
from core.migration.converter import convert
from core.operations.readiness import check_readiness
from core.sources.store import SourceStore, MAX_BYTES
from tools.vm_acceptance import hashes

STAMP = '2026-10-03T13:00:00Z'
DATA = b'PK\x03\x04Synthetic original\x00\xff'


def seed(root):
    FilesystemBackend(root / 'memory/persistent', root / 'memory/history')
    return SourceStore(root)


def add(store, content=DATA, **overrides):
    fields = dict(original_name='Manuscrit.docx', title='Mon manuscrit', author='Auteur', added_at=STAMP)
    fields.update(overrides)
    return store.add(content, **fields)


def test_exact_original_metadata_dedup_and_new_version(tmp_path):
    store = seed(tmp_path)
    before = {k:v for k,v in hashes(tmp_path / 'memory/persistent').items() if k != '.write.lock'}, hashes(tmp_path / 'memory/history')
    result = add(store)
    assert result['status'] == 'ADDED'
    identity = sha256(DATA).hexdigest()
    record, original = store.read(identity)
    assert original == DATA and record['source_id'] == identity
    assert record['original_name'] == 'Manuscrit.docx' and record['size'] == len(DATA)
    assert record['author'] == 'Auteur' and record['added_at'] == STAMP
    assert add(store, title='Changed title')['status'] == 'UNCHANGED'
    assert store.read(identity)[0] == record
    new = add(store, DATA + b' corrected')
    assert new['source']['source_id'] != identity and len(store.list()) == 2
    assert ({k:v for k,v in hashes(tmp_path / 'memory/persistent').items() if k != '.write.lock'}, hashes(tmp_path / 'memory/history')) == before
    assert check_readiness(tmp_path)['ready']


def test_list_missing_library_is_read_only(tmp_path):
    store = seed(tmp_path)
    before = hashes(tmp_path)
    assert store.list() == []
    assert hashes(tmp_path) == before and not store.directory.exists()


@pytest.mark.parametrize('content,fields', [
    (b'', {}), (b'x' * (MAX_BYTES + 1), {}), (DATA, {'original_name': '../other.docx'}),
    (DATA, {'original_name': 'bad\n.docx'}), (DATA, {'original_name': 'program.exe'}),
    (DATA, {'title': ''}), (DATA, {'author': 'x' * 257}),
    (DATA, {'added_at': '2026-10-03'}),
], ids=['empty', 'oversize', 'traversal', 'control', 'unsupported', 'title', 'author', 'timezone'])
def test_invalid_inputs_do_not_publish(tmp_path, content, fields):
    store = seed(tmp_path)
    before = hashes(tmp_path)
    with pytest.raises(ValueError):
        add(store, content, **fields)
    assert hashes(tmp_path) == before and not store.directory.exists()


def test_changed_original_and_unknown_source_block_readiness(tmp_path):
    store = seed(tmp_path)
    record = add(store)['source']
    path = store.directory / record['source_id'] / 'original'
    path.write_bytes(b'changed')
    with pytest.raises(ValueError):
        store.read(record['source_id'])
    assert not check_readiness(tmp_path)['ready']


def test_source_symlink_is_refused_without_touching_target(tmp_path):
    store = seed(tmp_path)
    outside = tmp_path / 'outside'
    outside.mkdir()
    store.directory.symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValueError):
        add(store)
    assert not list(outside.iterdir())
    assert not check_readiness(tmp_path)['ready']


def test_core_copy_preserves_source_bytes_and_fiche(tmp_path):
    root = tmp_path / 'source'
    root.mkdir()
    store = seed(root)
    record = add(store)['source']
    target = tmp_path / 'target'
    assert copy_core(root, target)['status'] == 'COPIED'
    assert SourceStore(target).read(record['source_id']) == store.read(record['source_id'])
    assert check_readiness(target)['ready']


def test_legacy_converter_refuses_sources_before_destination_creation(tmp_path):
    source = tmp_path / 'source'
    source.mkdir()
    add(seed(source))
    destination = tmp_path / 'converted'
    result = convert(source, destination)
    assert result['blocked_before_writes'] and not destination.exists()


def test_after_staging_exception_can_resume_exact_bundle(tmp_path, monkeypatch):
    store = seed(tmp_path)
    def stop(stage):
        if stage == 'after_staging':
            raise RuntimeError('stop after durable preparation')
    monkeypatch.setattr(store, '_checkpoint', stop, raising=False)
    with pytest.raises(RuntimeError):
        add(store)
    assert not check_readiness(tmp_path)['ready']
    monkeypatch.setattr(store, '_checkpoint', lambda stage: None)
    assert add(store)['status'] == 'ADDED'
    assert check_readiness(tmp_path)['ready']


def add_worker(root, output):
    output.put(add(SourceStore(Path(root)))['status'])


def test_two_uploaders_converge_without_overwriting_original(tmp_path):
    store = seed(tmp_path)
    context = multiprocessing.get_context('fork')
    output = context.Queue()
    workers = [context.Process(target=add_worker, args=(str(tmp_path), output)) for _ in range(2)]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join(10)
        assert worker.exitcode == 0
    assert sorted(output.get(timeout=2) for _ in workers) == ['ADDED', 'UNCHANGED']
    assert len(store.list()) == 1 and store.read(sha256(DATA).hexdigest())[1] == DATA


def interrupted_upload(root):
    store = SourceStore(Path(root))
    store._checkpoint = lambda stage: os._exit(74) if stage == 'after_staging' else None
    add(store)


def test_real_process_stop_after_staging_retries_same_original(tmp_path):
    store = seed(tmp_path)
    worker = multiprocessing.get_context('fork').Process(target=interrupted_upload, args=(str(tmp_path),))
    worker.start()
    worker.join(10)
    assert worker.exitcode == 74 and not check_readiness(tmp_path)['ready']
    assert add(store)['status'] == 'ADDED'
    assert store.read(sha256(DATA).hexdigest())[1] == DATA
    assert check_readiness(tmp_path)['ready']


def test_core_copy_carries_frozen_text_extraction(tmp_path):
    source = tmp_path/'source'
    source.mkdir()
    store = seed(source)
    identity = add(store, b'line one\nline two', original_name='notes.txt')['source']['source_id']
    extracted = store.extract(identity)['extraction']
    target = tmp_path/'target'
    assert copy_core(source,target)['status'] == 'COPIED'
    assert SourceStore(target).extraction(identity) == extracted
    assert SourceStore(target).read(identity) == store.read(identity)


def test_frozen_extraction_survives_change_to_default_extractor(tmp_path, monkeypatch):
    import core.sources.extraction as module
    from core.operations.readiness import check_readiness
    store=seed(tmp_path)
    record=add(store,b'First paragraph\n\nSecond paragraph',original_name='frozen.txt')['source']
    frozen=store.extract(record['source_id'])['extraction']
    original=module.extract_paragraphs
    def newer(record,data):
        old=original(record,data)
        paragraphs=[text for text in old['paragraphs'] if text.strip()]
        from hashlib import sha256
        return dict(old,extractor='utf8-lines-v2',paragraphs=paragraphs,
                    text_sha256=sha256('\n'.join(paragraphs).encode()).hexdigest())
    before=hashes(tmp_path)
    monkeypatch.setattr(module,'extract_paragraphs',newer)
    assert store.extraction(record['source_id'])==frozen
    assert check_readiness(tmp_path)['ready'] and hashes(tmp_path)==before
