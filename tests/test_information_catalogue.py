from dataclasses import replace
import json
import multiprocessing
import os
from pathlib import Path
import subprocess
import sys

import pytest

from core.backend.filesystem import FilesystemBackend
from core.backend.models import Memory
from core.indexing.catalogue import InformationCatalogue
from core.information.writes import FilesystemInformationWrites
from core.operations.errors import OperationConflict
from core.operations.readiness import recover_all
from core.threads.models import Thread
from core.threads.storage import ThreadStorage
from tools.vm_acceptance import hashes


def seed(root):
    backend = FilesystemBackend(root / 'memory/persistent', root / 'memory/history')
    backend.store(Memory('pump', content='SECRET_BODY_ONLY', metadata={
        'type': 'HYPOTHESIS', 'epistemic_status': 'UNVERIFIED',
        'operational_state': 'ACTIVE', 'keywords': ['pompe', 'silence'],
        'availability': 'LOW', 'retention': 'LONG_TERM',
        'qualification': {'nature': 'TECHNICAL'}, 'context': {'scope': {'place_id': 'cave'}},
        'private_extension': 'SECRET_EXTENSION_ONLY'}, temporal={'resume_at': '2026-10-02T06:00:00+02:00'}))
    return backend, InformationCatalogue(root)


def test_rebuild_is_deterministic_disposable_and_contains_only_metadata(tmp_path):
    backend, catalogue = seed(tmp_path)
    before = hashes(tmp_path)
    assert catalogue.status()['status'] == 'MISSING'
    assert hashes(tmp_path) == before
    assert not catalogue.directory.exists()
    assert catalogue.rebuild()['status'] == 'REBUILT'
    original = catalogue.path.read_bytes()
    assert b'SECRET_BODY_ONLY' not in original and b'SECRET_EXTENSION_ONLY' not in original
    item = catalogue.query('pompe', availability='LOW')[0]
    assert item['nature'] == 'TECHNICAL' and item['epistemic_status'] == 'UNVERIFIED'
    assert item['pointer'] == 'memory/persistent/pump.md'
    assert item['temporal']['resume_at'].endswith('+02:00')
    assert item['context']['scope']['place_id'] == 'cave'
    assert catalogue.query('SECRET_BODY_ONLY') == []
    assert catalogue.rebuild()['status'] == 'UNCHANGED'
    catalogue.path.unlink()
    assert catalogue.rebuild()['status'] == 'REBUILT'
    assert catalogue.path.read_bytes() == original
    assert catalogue.query('pompe', availability='LOW')[0] == item


def test_correction_blocks_stale_search_and_rebuild_removes_old_keywords(tmp_path):
    backend, catalogue = seed(tmp_path)
    catalogue.rebuild()
    current = backend.get('pump')
    backend.update('pump', replace(current, metadata=dict(current.metadata, keywords=['ventilateur'])), 1)
    assert catalogue.status()['status'] == 'STALE'
    with pytest.raises(OperationConflict, match='STALE'):
        catalogue.query('pompe')
    catalogue.rebuild()
    assert catalogue.query('pompe') == []
    assert catalogue.query('ventilateur')[0]['revision'] == 2
    assert 'pompe' not in catalogue.path.read_text()


def test_pending_deletion_is_excluded_and_approved_deletion_disappears(tmp_path):
    backend, catalogue = seed(tmp_path)
    catalogue.rebuild()
    backend.delete_request('pump', 'human', 'obsolete', 1, 'remove')
    assert catalogue.status()['status'] == 'STALE'
    catalogue.rebuild()
    assert catalogue.query() == []
    assert json.loads(catalogue.path.read_text())['entries'][0]['deletion_status'] == 'PENDING_DELETE'
    backend.approve_delete('pump', 'remove')
    with pytest.raises(OperationConflict):
        catalogue.query()
    catalogue.rebuild()
    assert json.loads(catalogue.path.read_text())['entries'] == []
    assert 'pompe' not in catalogue.path.read_text() and backend.get('pump') is None


def test_cancelled_deletion_becomes_discoverable_again(tmp_path):
    backend, catalogue = seed(tmp_path)
    backend.delete_request('pump', 'human', 'obsolete', 1, 'remove')
    catalogue.rebuild()
    backend.cancel_delete('pump', 'remove')
    assert catalogue.status()['status'] == 'STALE'
    catalogue.rebuild()
    assert catalogue.query()[0]['deletion_status'] == 'CANCELLED'


def test_project_membership_comes_from_threads_and_changes_invalidate_catalogue(tmp_path):
    backend, catalogue = seed(tmp_path)
    storage = ThreadStorage(backend.persistent_root)
    storage.create(Thread('cooling', 'Cool', 'Project', relations=[{'type': 'CONCERNS', 'target_id': 'pump'}]))
    catalogue.rebuild()
    assert catalogue.query(project_id='cooling')[0]['information_id'] == 'pump'
    assert catalogue.query(project_id='other') == []
    storage.delete('cooling', previous_revision=1, operation_id='delete-thread')
    assert catalogue.status()['status'] == 'STALE'
    catalogue.rebuild()
    assert catalogue.query()[0]['project_ids'] == []


def test_direct_edit_without_revision_is_detected(tmp_path):
    backend, catalogue = seed(tmp_path)
    catalogue.rebuild()
    source = backend._path('pump')
    source.write_text(source.read_text().replace('silence', 'bruit'))
    assert catalogue.status()['status'] == 'STALE'
    catalogue.rebuild()
    assert catalogue.query('bruit')[0]['revision'] == 1


@pytest.mark.parametrize('corruption', ['{', '{"format_version":999}', 'tamper'])
def test_corrupted_or_tampered_catalogue_never_returns_old_data(tmp_path, corruption):
    _, catalogue = seed(tmp_path)
    catalogue.rebuild()
    if corruption == 'tamper':
        data = json.loads(catalogue.path.read_text())
        data['entries'][0]['keywords'] = ['faux']
        corruption = json.dumps(data)
    catalogue.path.write_text(corruption)
    with pytest.raises(OperationConflict):
        catalogue.query()
    catalogue.rebuild()
    assert catalogue.query('pompe') and not catalogue.query('faux')


def test_unfinished_write_blocks_rebuild_until_recovered(tmp_path, monkeypatch):
    backend, catalogue = seed(tmp_path)
    catalogue.rebuild()
    original = catalogue.path.read_bytes()
    writer = FilesystemInformationWrites(backend)
    with monkeypatch.context() as patch:
        patch.setattr(writer.events, 'save', lambda event: (_ for _ in ()).throw(RuntimeError('stop')))
        with pytest.raises(RuntimeError):
            writer.update(replace(backend.get('pump'), content='New body'), previous_revision=1,
                          operation_id='update', event_id='updated', actor='human', timestamp='fixed')
    with pytest.raises(OperationConflict, match='readiness'):
        catalogue.rebuild()
    assert catalogue.path.read_bytes() == original
    assert recover_all(tmp_path)['readiness']['ready']
    catalogue.rebuild()
    assert catalogue.query()[0]['revision'] == 2


@pytest.mark.parametrize('boundary', ['before', 'after'])
def test_atomic_publication_can_be_retried_without_source_writes(tmp_path, monkeypatch, boundary):
    backend, catalogue = seed(tmp_path)
    catalogue.rebuild()
    current = backend.get('pump')
    backend.update('pump', replace(current, content='Changed'), 1)
    canonical = hashes(backend.persistent_root), hashes(backend.history_root)
    import core.indexing.catalogue as module
    original = module.atomic_write_text
    def stop(path, text):
        if boundary == 'after':
            original(path, text)
        raise RuntimeError('stop')
    with monkeypatch.context() as patch:
        patch.setattr(module, 'atomic_write_text', stop)
        with pytest.raises(RuntimeError):
            catalogue.rebuild()
    assert catalogue.status()['status'] == ('STALE' if boundary == 'before' else 'CURRENT')
    catalogue.rebuild()
    assert catalogue.query()[0]['revision'] == 2
    assert (hashes(backend.persistent_root), hashes(backend.history_root)) == canonical


def crash_publication(root):
    import core.indexing.catalogue as module
    original = module.atomic_write_text
    def stop(path, text):
        original(path, text)
        os._exit(74)
    module.atomic_write_text = stop
    InformationCatalogue(Path(root)).rebuild()


def test_process_exit_after_publication_leaves_reusable_catalogue(tmp_path):
    _, catalogue = seed(tmp_path)
    child = multiprocessing.get_context('spawn').Process(target=crash_publication, args=(str(tmp_path),))
    child.start()
    try:
        child.join(15)
        assert child.exitcode == 74
    finally:
        if child.is_alive():
            child.terminate()
            child.join()
    assert catalogue.rebuild()['status'] == 'UNCHANGED'
    assert catalogue.query('pompe')


def test_cli_reports_missing_without_writes_then_rebuilds_and_filters(tmp_path):
    _, catalogue = seed(tmp_path)
    command = [sys.executable, '-B', '-m', 'core.indexing.catalogue_cli', '--root', str(tmp_path)]
    before = hashes(tmp_path)
    status = subprocess.run([*command, 'status'], text=True, capture_output=True)
    assert status.returncode == 1 and json.loads(status.stdout)['status'] == 'MISSING'
    assert hashes(tmp_path) == before
    assert subprocess.run([*command, 'rebuild'], capture_output=True).returncode == 0
    query = subprocess.run([*command, 'query', 'pompe', '--availability', 'LOW'], text=True, capture_output=True)
    assert query.returncode == 0 and json.loads(query.stdout)['items'][0]['information_id'] == 'pump'


def test_symlink_output_is_not_replaced(tmp_path):
    _, catalogue = seed(tmp_path)
    catalogue.directory.mkdir()
    external = tmp_path / 'external'
    external.write_text('human')
    catalogue.path.symlink_to(external)
    with pytest.raises(OperationConflict):
        catalogue.rebuild()
    assert external.read_text() == 'human'


def test_unknown_availability_is_not_inferred_from_retention(tmp_path):
    backend, catalogue = seed(tmp_path)
    backend.store(Memory('unknown', content='Hidden', metadata={'retention': 'LONG_TERM', 'keywords': ['pompe']}))
    catalogue.rebuild()
    assert [row['information_id'] for row in catalogue.query(availability='LOW')] == ['pump']
    assert len(catalogue.query('pompe')) == 2
    assert catalogue.query(epistemic_status='CONFIRMED') == []


def test_catalogue_decodes_each_source_once_but_checks_both_reads(tmp_path, monkeypatch):
    import core.indexing.catalogue as module
    backend, catalogue = seed(tmp_path)
    monkeypatch.setattr(module, 'check_readiness', lambda root: {'ready': True})
    original = FilesystemBackend._deserialize
    parsed = []
    reads = []
    read_bytes = Path.read_bytes

    def tracked_parse(raw):
        parsed.append(raw)
        return original(raw)

    def tracked_read(path):
        if path == backend._path('pump'):
            reads.append(path)
        return read_bytes(path)

    monkeypatch.setattr(FilesystemBackend, '_deserialize', staticmethod(tracked_parse))
    monkeypatch.setattr(Path, 'read_bytes', tracked_read)
    snapshot = catalogue._snapshot()
    assert snapshot['entries'][0]['information_id'] == 'pump'
    assert len(reads) == 2 and len(parsed) == 1
    assert 'SECRET_BODY_ONLY' not in json.dumps(snapshot)
    assert 'SECRET_EXTENSION_ONLY' not in json.dumps(snapshot)


def test_catalogue_refuses_changed_bytes_between_manifest_and_projection(tmp_path, monkeypatch):
    import core.indexing.catalogue as module
    backend, catalogue = seed(tmp_path)
    monkeypatch.setattr(module, 'check_readiness', lambda root: {'ready': True})
    original = Path.read_bytes
    count = 0

    def changed(path):
        nonlocal count
        raw = original(path)
        if path == backend._path('pump'):
            count += 1
            if count == 2:
                return raw.replace(b'SECRET_BODY_ONLY', b'CHANGED_BODY_ONLY')
        return raw

    monkeypatch.setattr(Path, 'read_bytes', changed)
    before = hashes(tmp_path)
    with pytest.raises(OperationConflict, match='source changed'):
        catalogue._snapshot()
    assert hashes(tmp_path) == before
