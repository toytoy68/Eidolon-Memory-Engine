"""Claude negative review of F1/F1b (53d5047): durable extraction commitments.

Synthetic sources only. Cases are named after the expected contract; a failure is a
defect or a limit to report. No real corpus, no manuscript, no service.
"""
import base64
import json
import multiprocessing
import os
import threading
import urllib.request
from http.server import ThreadingHTTPServer

import pytest

from core.operations.readiness import check_readiness
from core.sources.commitments import directory
from core.sources.extraction import reproduce_extraction
from core.sources.store import SourceStore, audit_sources
from core.sources.validation import accept_detail
from tests.test_source_library import seed, add, STAMP

TEXT = ('Lina habite à Lyon.\nElle possède' + chr(0x0c) + 'un chat nommé Plume.\nFin secrète.\n').encode()


def new_source(root, text=TEXT, name='story.txt'):
    store = seed(root)
    return store, add(store, text, original_name=name, title=name)['source']


def commitment(root, identity):
    return directory(root) / (identity + '.json')


def substitute_with_v1(store, record):
    path = store.directory / record['source_id'] / 'extraction.json'
    original = (store.directory / record['source_id'] / 'original').read_bytes()
    v1 = reproduce_extraction(record, original, extractor='utf8-lines-v1')
    path.write_text(json.dumps(v1, ensure_ascii=False, sort_keys=True) + '\n', encoding='utf-8')


def issues(root):
    return check_readiness(root)['issues']


# --- resumption ----------------------------------------------------------------

def test_two_pending_extractions_can_each_be_resumed(tmp_path):
    """Two committed sources whose extraction.json vanished (e.g. partial restore)."""
    store, a = new_source(tmp_path)
    b = add(store, TEXT + b'Autre.\n', original_name='b.txt', title='b')['source']
    for record in (a, b):
        store.extract(record['source_id'])
    for record in (a, b):
        (store.directory / record['source_id'] / 'extraction.json').unlink()
    reasons = sorted(i['reason'] for i in issues(tmp_path))
    assert reasons == ['pending_source_extraction', 'pending_source_extraction']
    store.extract(a['source_id'])  # must not be refused because b is also pending
    store.extract(b['source_id'])
    assert check_readiness(tmp_path)['ready']


def test_resume_preserves_commitment_bytes_and_timestamp(tmp_path):
    store, record = new_source(tmp_path)
    store.extract(record['source_id'])
    before = commitment(tmp_path, record['source_id']).read_bytes()
    (store.directory / record['source_id'] / 'extraction.json').unlink()
    store.extract(record['source_id'])
    assert commitment(tmp_path, record['source_id']).read_bytes() == before


def _die_inside_commitment_write(root, identity):
    """Real death after the temporary commitment file exists, before its rename."""
    import core.persistence as persistence
    import core.sources.store as store_module
    def replace(source, destination):
        if 'source-extractions-v1' in str(destination):
            os._exit(9)
        return original(source, destination)
    original = persistence.durable_replace
    persistence.durable_replace = replace
    SourceStore(root).extract(identity)
    os._exit(0)


def test_death_inside_commitment_write_is_blocked_and_explained(tmp_path):
    """Characterization: a temporary residue blocks; nothing is published; no silent loss."""
    store, record = new_source(tmp_path)
    if 'fork' not in multiprocessing.get_all_start_methods():
        pytest.skip('requires fork for process interruption')
    p = multiprocessing.get_context('fork').Process(target=_die_inside_commitment_write, args=(tmp_path, record['source_id']))
    p.start(); p.join(60)
    assert p.exitcode == 9
    assert not commitment(tmp_path, record['source_id']).exists()
    assert not (store.directory / record['source_id'] / 'extraction.json').exists()
    residues = [p.name for p in directory(tmp_path).iterdir() if p.name.endswith('.tmp')]
    assert residues, 'expected the atomic-write temporary residue'
    found = issues(tmp_path)
    assert found and {i['reason'] for i in found} <= {'invalid extraction commitment entry', 'unknown_history_file'}, found
    assert not any(i.get('resumable') for i in found)  # needs a human: not resumable by extract()
    with pytest.raises(ValueError):
        store.extract(record['source_id'])


# --- tampering -----------------------------------------------------------------

@pytest.mark.parametrize('mutation', ['drop_field', 'naive_time', 'other_extractor', 'zero_paragraphs', 'not_json'])
def test_malformed_commitment_blocks_without_crashing(tmp_path, mutation):
    store, record = new_source(tmp_path)
    store.extract(record['source_id'])
    path = commitment(tmp_path, record['source_id'])
    data = json.loads(path.read_text(encoding='utf-8'))
    if mutation == 'drop_field':
        data.pop('committed_at')
    elif mutation == 'naive_time':
        data['committed_at'] = '2026-10-04T10:00:00'
    elif mutation == 'other_extractor':
        data['extractor'] = 'utf8-lines-v1'
    elif mutation == 'zero_paragraphs':
        data['paragraph_count'] = 0
    text = '{not json' if mutation == 'not_json' else json.dumps(data, sort_keys=True) + '\n'
    path.write_text(text, encoding='utf-8')
    state = check_readiness(tmp_path)
    assert not state['ready']
    with pytest.raises(ValueError):
        store.extraction(record['source_id'])


def test_symlinked_commitment_or_family_blocks(tmp_path):
    store, record = new_source(tmp_path)
    store.extract(record['source_id'])
    path = commitment(tmp_path, record['source_id'])
    outside = tmp_path / 'outside.json'
    outside.write_bytes(path.read_bytes())
    path.unlink(); os.symlink(outside, path)
    assert not check_readiness(tmp_path)['ready']


def test_symlinked_family_directory_blocks(tmp_path):
    store, record = new_source(tmp_path)
    store.extract(record['source_id'])
    family = directory(tmp_path)
    moved = tmp_path / 'moved-family'
    family.rename(moved); os.symlink(moved, family)
    assert not check_readiness(tmp_path)['ready']


def test_stray_file_in_family_blocks(tmp_path):
    store, record = new_source(tmp_path)
    store.extract(record['source_id'])
    (directory(tmp_path) / 'notes.txt').write_text('x', encoding='utf-8')
    assert not check_readiness(tmp_path)['ready']


def test_removing_both_commitment_and_extraction_returns_to_free_state(tmp_path, monkeypatch):
    """Characterization (limit): deleting the promise with the text is not detectable;
    a validated detail then warns through F1a if the new default differs."""
    import core.sources.extraction as extraction_module
    store, record = new_source(tmp_path)
    extraction = store.extract(record['source_id'])['extraction']
    accept_detail(tmp_path, dict(source_id=record['source_id'], source_sha256=record['sha256'],
        extraction_sha256=extraction['text_sha256'], extractor=extraction['extractor'], model='m',
        model_digest='a' * 64, proposed_at=STAMP, paragraph=3, detail='La fin.', quote='Fin secrète.'),
        detail='La fin.', actor='human')
    commitment(tmp_path, record['source_id']).unlink()
    (store.directory / record['source_id'] / 'extraction.json').unlink()
    assert check_readiness(tmp_path)['ready']
    monkeypatch.setitem(extraction_module._DEFAULT_EXTRACTORS, '.txt', 'utf8-lines-v1')
    store.extract(record['source_id'])
    assert check_readiness(tmp_path)['ready']
    assert audit_sources(tmp_path)['warnings'], 'F1a must still warn about the moved paragraph'


# --- concurrency ---------------------------------------------------------------

def _worker(root, identity, action, barrier, queue):
    barrier.wait()
    try:
        store = SourceStore(root)
        queue.put(getattr(store, action)(identity)['status'])
    except Exception as exc:
        queue.put(f'{type(exc).__name__}: {exc}')


def run_concurrently(root, identity, action, n):
    if 'fork' not in multiprocessing.get_all_start_methods():
        pytest.skip('requires fork for synchronized concurrency')
    ctx = multiprocessing.get_context('fork')
    barrier, queue = ctx.Barrier(n), ctx.Queue()
    procs = [ctx.Process(target=_worker, args=(root, identity, action, barrier, queue)) for _ in range(n)]
    try:
        for p in procs: p.start()
        results = sorted(queue.get(timeout=20) for _ in procs)
        for p in procs:
            p.join(20)
            assert p.exitcode == 0
        return results
    finally:
        for p in procs:
            if p.is_alive(): p.terminate()
            if p.pid is not None: p.join(5)
        queue.close()
        queue.join_thread()


def test_concurrent_first_extractions_publish_one_commitment(tmp_path):
    store, record = new_source(tmp_path)
    results = run_concurrently(tmp_path, record['source_id'], 'extract', 4)
    assert results.count('EXTRACTED') == 1 and results.count('UNCHANGED') == 3, results
    assert len([p for p in directory(tmp_path).iterdir() if p.name.endswith('.json')]) == 1
    assert check_readiness(tmp_path)['ready']


def test_concurrent_explicit_commits_publish_once(tmp_path):
    store, record = new_source(tmp_path)
    store.extract(record['source_id'])
    commitment(tmp_path, record['source_id']).unlink()  # legacy bundle
    results = run_concurrently(tmp_path, record['source_id'], 'commit_extraction', 3)
    assert results.count('COMMITTED') == 1 and results.count('UNCHANGED') == 2, results
    assert check_readiness(tmp_path)['ready']


# --- explicit commit CLI and HTTP ----------------------------------------------

def test_cli_preview_writes_nothing_then_apply_commits(tmp_path, capsys):
    from tools.commit_source_extraction import main
    from tools.vm_acceptance import hashes
    store, record = new_source(tmp_path)
    store.extract(record['source_id'])
    commitment(tmp_path, record['source_id']).unlink()
    before = {k: v for k, v in hashes(tmp_path).items() if not k.endswith('.write.lock')}
    assert main(['--root', str(tmp_path), '--id', record['source_id']]) == 0
    assert json.loads(capsys.readouterr().out)['status'] == 'PREVIEW'
    assert {k: v for k, v in hashes(tmp_path).items() if not k.endswith('.write.lock')} == before
    assert main(['--root', str(tmp_path), '--id', record['source_id'], '--apply']) == 0
    assert json.loads(capsys.readouterr().out)['status'] == 'COMMITTED'
    assert main(['--root', str(tmp_path), '--id', '../' + 'a' * 61]) == 1


def test_dashboard_survives_a_blocked_commitment_without_leaking(tmp_path):
    from core.monitoring.dashboard import handler_factory
    store, record = new_source(tmp_path)
    store.extract(record['source_id'])
    substitute_with_v1(store, record)
    server = ThreadingHTTPServer(('127.0.0.1', 0), handler_factory(tmp_path, 'test-token'))
    thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
    auth = 'Basic ' + base64.b64encode(b'eidolon:test-token').decode()
    try:
        for path in ('/', '/sources', '/source?id=' + record['source_id'], '/source/text?id=' + record['source_id']):
            request = urllib.request.Request(f'http://127.0.0.1:{server.server_port}{path}', headers={'Authorization': auth})
            try:
                with urllib.request.urlopen(request, timeout=10) as response:
                    status, body = response.status, response.read().decode('utf-8', 'replace')
            except urllib.error.HTTPError as exc:
                status, body = exc.code, exc.read().decode('utf-8', 'replace')
            assert status != 500 and 'Traceback' not in body, (path, status)
            assert 'Fin secrète' not in body or path.startswith('/source/text'), path
    finally:
        server.shutdown(); server.server_close()


def test_fresh_extraction_still_refused_while_another_is_pending(tmp_path):
    store, a = new_source(tmp_path)
    fresh = add(store, TEXT + b'Neuf.\n', original_name='c.txt', title='c')['source']
    store.extract(a['source_id'])
    (store.directory / a['source_id'] / 'extraction.json').unlink()
    with pytest.raises(ValueError, match='readiness'):
        store.extract(fresh['source_id'])
    assert not (store.directory / fresh['source_id'] / 'extraction.json').exists()


def test_pending_resume_refused_when_another_issue_exists(tmp_path):
    store, a = new_source(tmp_path)
    b = add(store, TEXT + b'Autre.\n', original_name='b.txt', title='b')['source']
    store.extract(a['source_id']); store.extract(b['source_id'])
    (store.directory / a['source_id'] / 'extraction.json').unlink()
    substitute_with_v1(store, b)  # a blocking mismatch elsewhere
    with pytest.raises(ValueError, match='readiness'):
        store.extract(a['source_id'])
