import json
import pytest
from core.sources.store import audit_sources
from core.sources.extraction import reproduce_extraction
from core.sources.validation import accept_detail
from core.operations.readiness import check_readiness
from core.monitoring.sources import render_sources, render_source
from tests.test_source_library import seed, add
from tests.test_source_ai import review
from tools.vm_acceptance import hashes


@pytest.mark.parametrize('legacy', [False, True])
def test_valid_then_substituted_extraction_warns_without_writes(tmp_path, legacy):
    store = seed(tmp_path)
    record = add(store, 'Lina habite à Lyon.\nElle possède\fun chat nommé Plume.\nFin.\n'.encode(), original_name='story.txt')['source']
    extraction = store.extract(record['source_id'])['extraction']
    draft = dict(review(record, extraction), paragraph=3, quote='Fin.')
    if legacy:
        from tests.test_source_detail_identity import seed_v1
        result, _, _ = seed_v1(tmp_path, draft)
    else:
        result = accept_detail(tmp_path, draft, detail=draft['detail'], actor='human')
    before = hashes(tmp_path)
    assert audit_sources(tmp_path)['warnings'] == []
    assert check_readiness(tmp_path)['ready']
    assert hashes(tmp_path) == before
    from core.sources.commitments import directory
    (directory(tmp_path) / (record['source_id'] + '.json')).unlink()
    original = store.read(record['source_id'])[1]
    old = reproduce_extraction(record, original, extractor='utf8-lines-v1')
    (store.directory / record['source_id'] / 'extraction.json').write_text(json.dumps(old))
    before = hashes(tmp_path)
    report = audit_sources(tmp_path)
    warning, = report['warnings']
    assert not report['issues']
    assert warning['information_id'] == result['information_id']
    assert set(warning['mismatches']) == {'extractor_mismatch', 'extraction_sha256_mismatch', 'quote_mismatch'}
    state = check_readiness(tmp_path)
    assert state['ready'] and state['warnings'] == report['warnings']
    for page in (render_sources([record], warnings=report['warnings']),
                 render_source(record, warnings=report['warnings'])):
        assert warning['information_id'] in page and 'source_reference_mismatch' in page
        assert draft['detail'] not in page and draft['quote'] not in page
    assert hashes(tmp_path) == before


def test_corrupt_extraction_still_blocks(tmp_path):
    from tests.test_source_ai import setup
    store, record, extraction = setup(tmp_path)
    draft = review(record, extraction)
    accept_detail(tmp_path, draft, detail=draft['detail'], actor='human')
    (store.directory / record['source_id'] / 'extraction.json').write_text('{}')
    before = hashes(tmp_path)
    assert audit_sources(tmp_path)['issues']
    assert not check_readiness(tmp_path)['ready']
    assert hashes(tmp_path) == before


def test_deleted_detail_does_not_warn_and_empty_audit_creates_nothing(tmp_path):
    from tests.test_source_ai import setup
    assert audit_sources(tmp_path)['warnings'] == []
    assert list(tmp_path.iterdir()) == []
    store, record, extraction = setup(tmp_path)
    draft = review(record, extraction)
    result = accept_detail(tmp_path, draft, detail=draft['detail'], actor='human')
    from core.backend.filesystem import FilesystemBackend
    backend = FilesystemBackend(tmp_path/'memory/persistent', tmp_path/'memory/history')
    backend.delete_request(result['information_id'], 'human', 'remove', 1, 'delete-detail')
    from core.information.writes import FilesystemInformationWrites
    writer = FilesystemInformationWrites(backend)
    for opid in writer.journal.ids():
        writer.compact(opid)
    backend.approve_delete(result['information_id'], 'delete-detail')
    before = hashes(tmp_path)
    assert audit_sources(tmp_path)['warnings'] == []
    assert hashes(tmp_path) == before


def test_http_warning_counter_library_and_source_are_read_only(tmp_path):
    from tests.test_source_ai import setup
    from tests.test_dashboard_sources import server, request
    store, record, extraction = setup(tmp_path)
    draft = review(record, extraction)
    result = accept_detail(tmp_path, draft, detail=draft['detail'], actor='human')
    from core.backend.filesystem import FilesystemBackend
    backend = FilesystemBackend(tmp_path/'memory/persistent', tmp_path/'memory/history')
    memory = backend.get(result['information_id'])
    memory.provenance['extraction_sha256'] = '0'*64
    backend.update(memory.information_id, memory, memory.revision)
    before = hashes(tmp_path)
    with server(tmp_path, writable=False) as port:
        status, _, page = request(port, '/')
        assert status == 200 and 'Références à vérifier : 1'.encode() in page
        for path in ('/sources', '/source?id='+record['source_id']):
            status, _, page = request(port, path)
            assert status == 200 and b'source_reference_mismatch' in page
            assert result['information_id'].encode() in page
            assert draft['detail'].encode() not in page and draft['quote'].encode() not in page
        assert request(port, '/sources', auth=False)[0] == 401
    assert hashes(tmp_path) == before


def test_shared_source_is_reproduced_once_per_audit(tmp_path, monkeypatch):
    from tests.test_source_ai import setup
    import core.sources.extraction as module
    store, record, extraction = setup(tmp_path)
    draft = review(record, extraction)
    for detail in ('Premier détail.', 'Second détail.'):
        accept_detail(tmp_path, draft, detail=detail, actor='human')
    calls = []
    original = module.reproduce_extraction
    def counted(*args, **kwargs):
        calls.append(args[0]['source_id'])
        return original(*args, **kwargs)
    monkeypatch.setattr(module, 'reproduce_extraction', counted)
    assert audit_sources(tmp_path)['warnings'] == []
    assert calls == [record['source_id']]
    audit_sources(tmp_path)
    assert calls == [record['source_id'], record['source_id']]
