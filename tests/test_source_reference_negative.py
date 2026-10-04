"""Claude negative review of F1a (f205708), updated for F1/F1b (53d5047): reference warnings.

Synthetic sources only. Each case states the expected contract from
SOURCE-REFERENCE-AUDIT-PLAN.md and toytoy's decisions (warning, never blocking).
"""
import json
import os
from hashlib import sha256

import pytest

from core.backend.filesystem import FilesystemBackend
from core.backend.models import Memory
from core.information.writes import FilesystemInformationWrites
from core.operations.readiness import check_readiness
from core.sources.extraction import reproduce_extraction
from core.sources.store import audit_sources
from core.sources.validation import accept_detail
from tests.test_source_library import seed, add, STAMP

TEXT = ('Lina habite à Lyon.\nElle possède' + chr(0x0c) + 'un chat nommé Plume.\nFin secrète du récit.\n').encode()
DETAIL = 'DETAIL-PRIVE-NE-PAS-AFFICHER'
QUOTE = 'Fin secrète du récit.'


def prepared(root):
    store = seed(root)
    record = add(store, TEXT, original_name='story.txt')['source']
    extraction = store.extract(record['source_id'])['extraction']
    draft = dict(source_id=record['source_id'], source_sha256=record['sha256'],
                 extraction_sha256=extraction['text_sha256'], extractor=extraction['extractor'],
                 model='m', model_digest='a' * 64, proposed_at=STAMP, paragraph=3, detail=DETAIL, quote=QUOTE)
    accepted = accept_detail(root, draft, detail=DETAIL, actor='human')
    return store, record, extraction, accepted


def substitute_with_v1(store, record):
    path = store.directory / record['source_id'] / 'extraction.json'
    original = (store.directory / record['source_id'] / 'original').read_bytes()
    v1 = reproduce_extraction(record, original, extractor='utf8-lines-v1')
    path.write_text(json.dumps(v1, ensure_ascii=False, sort_keys=True) + '\n', encoding='utf-8')


def backend(root):
    return FilesystemBackend(root / 'memory/persistent', root / 'memory/history')


def write_detail(root, provenance, key='b' * 64):
    """A source-detail Information with an arbitrary (possibly partial) provenance."""
    memory = Memory('source-detail-' + key, content='x',
                    metadata={'type': 'INTERPRETATION', 'epistemic_status': 'UNVERIFIED'}, provenance=provenance)
    FilesystemInformationWrites(backend(root)).create(
        memory, operation_id='op-' + key, event_id='ev-' + key, actor='t', timestamp=STAMP)
    return memory.information_id


def warnings_for(root, information_id):
    return [w for w in audit_sources(root)['warnings'] if w['information_id'] == information_id]


def test_valid_reference_gives_no_warning(tmp_path):
    prepared(tmp_path)
    assert audit_sources(tmp_path)['warnings'] == []
    assert check_readiness(tmp_path)['warnings'] == []


def make_legacy(root, record):
    """Since F1/F1b new extractions are committed; drop the commitment to model an older bundle."""
    path = root / 'memory/history/source-extractions-v1' / (record['source_id'] + '.json')
    if path.exists():
        path.unlink()


def test_legit_substitution_on_legacy_bundle_warns_and_keeps_ready(tmp_path):
    store, record, _, accepted = prepared(tmp_path)
    make_legacy(tmp_path, record)
    substitute_with_v1(store, record)
    found = warnings_for(tmp_path, accepted['information_id'])
    assert found and 'extractor_mismatch' in found[0]['mismatches']
    state = check_readiness(tmp_path)
    assert state['ready'] and state['warnings']


def test_legit_substitution_on_committed_bundle_blocks_and_still_warns(tmp_path):
    store, record, _, accepted = prepared(tmp_path)
    substitute_with_v1(store, record)
    assert not check_readiness(tmp_path)['ready']
    assert warnings_for(tmp_path, accepted['information_id'])


def test_partial_provenance_warns_without_crash(tmp_path):
    store, record, _, _ = prepared(tmp_path)
    iid = write_detail(tmp_path, {'source': record['source_id']})
    found = warnings_for(tmp_path, iid)
    assert found and found[0]['paragraph'] is None
    assert check_readiness(tmp_path)['ready']


@pytest.mark.parametrize('paragraph', [True, 0, -1, 10 ** 9, '3', 3.0])
def test_odd_paragraph_values_warn(tmp_path, paragraph):
    store, record, extraction, _ = prepared(tmp_path)
    provenance = dict(source=record['source_id'], source_sha256=record['sha256'], extractor=extraction['extractor'],
                      extraction_sha256=extraction['text_sha256'], paragraph=paragraph, quote=QUOTE)
    iid = write_detail(tmp_path, provenance)
    found = warnings_for(tmp_path, iid)
    assert found and 'paragraph_mismatch' in found[0]['mismatches']


@pytest.mark.parametrize('source', [None, '', '../../etc/passwd', 'A' * 64, 'c' * 64])
def test_absent_or_invalid_source_warns(tmp_path, source):
    prepared(tmp_path)
    iid = write_detail(tmp_path, {'source': source, 'paragraph': 1, 'quote': 'x'})
    found = warnings_for(tmp_path, iid)
    assert found and found[0]['mismatches'] == ['source_or_extraction_unavailable']
    assert found[0]['source_id'] in (None, 'c' * 64)
    assert check_readiness(tmp_path)['ready']


def test_deleted_detail_no_longer_warns(tmp_path):
    store, record, _, accepted = prepared(tmp_path)
    make_legacy(tmp_path, record)
    substitute_with_v1(store, record)
    b = backend(tmp_path)
    b.delete_request(accepted['information_id'], 'human', 'remove', 1, 'del-1')
    writer = FilesystemInformationWrites(b)
    for opid in writer.journal.ids():
        writer.compact(opid)
    b.approve_delete(accepted['information_id'], 'del-1')
    assert warnings_for(tmp_path, accepted['information_id']) == []


def test_corrupted_extraction_stays_blocking_and_detail_warns(tmp_path):
    store, record, extraction, accepted = prepared(tmp_path)
    path = store.directory / record['source_id'] / 'extraction.json'
    forged = dict(extraction, paragraphs=['autre'], text_sha256=sha256(b'autre').hexdigest())
    path.write_text(json.dumps(forged, ensure_ascii=False, sort_keys=True) + '\n', encoding='utf-8')
    report = audit_sources(tmp_path)
    assert report['issues']  # corruption remains an issue
    assert not check_readiness(tmp_path)['ready']
    assert warnings_for(tmp_path, accepted['information_id'])


def test_symlinked_detail_is_not_silently_trusted(tmp_path):
    """A symlink named like a detail is skipped by the audit; inventory must still flag it."""
    store, record, _, accepted = prepared(tmp_path)
    persistent = tmp_path / 'memory/persistent'
    target = tmp_path / 'outside.md'
    target.write_bytes((persistent / (accepted['information_id'] + '.md')).read_bytes())
    os.symlink(target, persistent / ('source-detail-' + 'd' * 64 + '.md'))
    assert not check_readiness(tmp_path)['ready']


def test_http_rendering_shows_no_private_text(tmp_path):
    from core.monitoring.sources import render_sources, render_source
    from core.monitoring.dashboard import render_dashboard
    store, record, _, accepted = prepared(tmp_path)
    make_legacy(tmp_path, record)
    substitute_with_v1(store, record)
    warnings = audit_sources(tmp_path)['warnings']
    inspection = store.inspect()
    pages = [render_sources(inspection['sources'], warnings=warnings),
             render_source(record, has_extraction=True, warnings=warnings)]
    for page in pages:
        assert accepted['information_id'] in page
        for secret in (DETAIL, QUOTE, 'Lina habite', 'Plume'):
            assert secret not in page
    metrics = dict(host='h', measured_at='2026-10-04T00:00:00+00:00', data_path='/x',
                   ram_bytes=dict(used=1, total=2, available=1), volume_bytes=dict(used=1, total=2, free=1),
                   engine_data=dict(files=1, bytes=1, symlinks_skipped=0))
    from core.monitoring.overview import overview
    home = render_dashboard(metrics, overview(tmp_path), warnings=warnings)
    assert 'Références à vérifier : 1' in home
    for secret in (DETAIL, QUOTE):
        assert secret not in home
