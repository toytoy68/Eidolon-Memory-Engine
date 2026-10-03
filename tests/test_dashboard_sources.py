from contextlib import contextmanager
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from threading import Thread
import re
from urllib.parse import urlencode

from core.monitoring.dashboard import handler_factory
from tests.test_monitoring_dashboard import basic
from tests.test_source_library import seed, DATA
from tools.vm_acceptance import hashes


def multipart(csrf, data=DATA, name='story.docx', title='Source <script>'):
    parts = []
    for key, value in [('csrf', csrf), ('title', title), ('author', 'Moi')]:
        parts.append(f'--BOUNDARY\r\nContent-Disposition: form-data; name="{key}"\r\n\r\n{value}\r\n'.encode())
    parts.append(f'--BOUNDARY\r\nContent-Disposition: form-data; name="file"; filename="{name}"\r\nContent-Type: application/octet-stream\r\n\r\n'.encode()+data+b'\r\n--BOUNDARY--\r\n')
    return b''.join(parts)


@contextmanager
def server(root, *, writable=True, ai=None):
    instance = ThreadingHTTPServer(('127.0.0.1', 0), handler_factory(root, 'secret', allow_source_upload=writable, local_ai=ai))
    worker = Thread(target=lambda: instance.serve_forever(poll_interval=.01), daemon=True)
    worker.start()
    try:
        yield instance.server_port
    finally:
        instance.shutdown()
        instance.server_close()
        worker.join(5)


def request(port, path, *, method='GET', body=None, auth=True, content_type=None):
    connection = HTTPConnection('127.0.0.1', port, timeout=5)
    headers = {'Authorization': basic('eidolon:secret')} if auth else {}
    if content_type:
        headers['Content-Type'] = content_type
    connection.request(method, path, body=body, headers=headers)
    response = connection.getresponse()
    result = response.status, dict(response.getheaders()), response.read()
    connection.close()
    return result


def test_authenticated_upload_list_and_exact_attachment(tmp_path):
    store = seed(tmp_path)
    with server(tmp_path) as port:
        assert request(port, '/sources', auth=False)[0] == 401
        status, headers, page = request(port, '/sources')
        assert status == 200 and b'Ajouter un fichier source' in page
        csrf = re.search(b'name="csrf" value="([^"]+)"', page)[1].decode()
        status, _, page = request(port, '/sources', method='POST', body=multipart(csrf), content_type='multipart/form-data; boundary=BOUNDARY')
        assert status == 200 and b'Source ajout' in page
        from core.monitoring.appearance import SCRIPT, SCRIPT_HASH
        assert b'<script>' not in page.replace(('<script>'+SCRIPT+'</script>').encode(), b'')
        assert b'&lt;script&gt;' in page
        assert "script-src 'sha256-"+SCRIPT_HASH+"'" in headers['Content-Security-Policy']
        identity = store.list()[0]['source_id']
        status, headers, original = request(port, '/source/original?id='+identity)
        assert status == 200 and original == DATA
        assert headers['Content-Type'] == 'application/octet-stream'
        assert headers['Content-Disposition'].startswith('attachment;')
        assert request(port, '/source/original?id='+identity, auth=False)[0] == 401
        assert request(port, '/source?id=../other')[0] == 404


def test_missing_runtime_dependency_returns_http_error_without_writes(tmp_path, monkeypatch):
    import builtins
    store = seed(tmp_path)
    original_import = builtins.__import__

    def missing_converter(name, *args, **kwargs):
        if name == 'core.migration.converter':
            raise ModuleNotFoundError("No module named 'yaml'")
        return original_import(name, *args, **kwargs)

    with server(tmp_path) as port:
        page = request(port, '/sources')[2]
        csrf = re.search(b'name="csrf" value="([^"]+)"', page)[1].decode()
        before = hashes(tmp_path)
        monkeypatch.setattr(builtins, '__import__', missing_converter)
        status, _, body = request(port, '/sources', method='POST', body=multipart(csrf),
                                  content_type='multipart/form-data; boundary=BOUNDARY')
        assert status == 500 and b'Dependance serveur manquante' in body
        assert hashes(tmp_path) == before and store.list() == []


def test_csrf_unauthorized_and_readonly_uploads_do_not_write(tmp_path):
    store = seed(tmp_path)
    with server(tmp_path) as port:
        before = hashes(tmp_path)
        assert request(port, '/sources', method='POST', auth=False, body=multipart('x'), content_type='multipart/form-data; boundary=BOUNDARY')[0] == 401
        assert request(port, '/sources', method='POST', body=multipart('wrong'), content_type='multipart/form-data; boundary=BOUNDARY')[0] == 400
        assert hashes(tmp_path) == before and store.list() == []
    with server(tmp_path, writable=False) as port:
        assert b'name="file"' not in request(port, '/sources')[2]
        assert request(port, '/sources', method='POST', body=multipart('x'))[0] == 403
        assert hashes(tmp_path) == before


def test_extraction_is_explicit_post_and_get_remains_read_only(tmp_path):
    store = seed(tmp_path)
    from tests.test_source_library import add
    identity = add(store, b'line one\nline two', original_name='test.txt')['source']['source_id']
    with server(tmp_path) as port:
        before = hashes(tmp_path)
        assert request(port, '/source/text?id='+identity)[0] == 404
        page = request(port, '/source?id='+identity)[2]
        assert hashes(tmp_path) == before
        csrf = re.search(b'name="csrf" value="([^"]+)"', page)[1].decode()
        body = urlencode({'id': identity, 'csrf': csrf})
        status, _, text = request(port, '/source/extract', method='POST', body=body, content_type='application/x-www-form-urlencoded')
        assert status == 200 and b'line one' in text
        before = hashes(tmp_path)
        assert request(port, '/source/text?id='+identity)[0] == 200
        assert hashes(tmp_path) == before


def test_ia_proposals_require_explicit_human_acceptance_and_signed_source(tmp_path):
    from tests.test_source_ai import setup
    from core.backend.filesystem import FilesystemBackend
    store, record, extracted = setup(tmp_path)
    class FakeAI:
        def propose(self, source, text, start):
            return dict(source_id=source['source_id'], source_sha256=source['sha256'],
                extraction_sha256=text['text_sha256'], extractor=text['extractor'],
                model='qwen3:0.6b', model_digest='a'*64, first_paragraph=1,last_paragraph=2,next_paragraph=None,
                details=[dict(detail='Lina vit à Lyon.',paragraph=1,quote='Lina habite à Lyon.')])
    backend = FilesystemBackend(tmp_path/'memory/persistent',tmp_path/'memory/history')
    with server(tmp_path, ai=FakeAI()) as port:
        page=request(port,'/source/text?id='+record['source_id'])[2]
        csrf=re.search(b'name="csrf" value="([^"]+)"',page)[1].decode()
        before=hashes(tmp_path)
        status,_,page=request(port,'/source/propose',method='POST',
            body=urlencode({'id':record['source_id'],'csrf':csrf,'start':1}),content_type='application/x-www-form-urlencoded')
        assert status==200 and b'Valider ce d' in page
        assert hashes(tmp_path)==before and not list(backend.persistent_root.glob('*.md'))
        token=re.search(b'name="review" value="([^"]+)"',page)[1].decode()
        status,_,_=request(port,'/source/accept',method='POST',
            body=urlencode({'csrf':csrf,'review':token+'x','detail':'Dans ce récit, Lina vit à Lyon.'}),content_type='application/x-www-form-urlencoded')
        assert status==400 and hashes(tmp_path)==before
        body=urlencode({'csrf':csrf,'review':token,'detail':'Dans ce récit, Lina vit à Lyon.'})
        assert request(port,'/source/accept',method='POST',body=body,content_type='application/x-www-form-urlencoded')[0]==200
        assert len(list(backend.persistent_root.glob('*.md')))==1
        stable=hashes(tmp_path)
        assert request(port,'/source/accept',method='POST',body=body,content_type='application/x-www-form-urlencoded')[0]==200
        assert hashes(tmp_path)==stable


def test_next_passage_button_continues_analysis_without_memory_write(tmp_path):
    from tests.test_source_ai import setup
    _, record, _ = setup(tmp_path)
    starts = []
    class FakeAI:
        def propose(self, source, text, start):
            starts.append(start)
            return dict(source_id=source['source_id'], source_sha256=source['sha256'],
                extraction_sha256=text['text_sha256'], extractor=text['extractor'],
                model='qwen3:0.6b', model_digest='a'*64, first_paragraph=start,
                last_paragraph=start, next_paragraph=2 if start == 1 else None, details=[])
    with server(tmp_path, ai=FakeAI()) as port:
        page = request(port, '/source/text?id='+record['source_id'])[2]
        csrf = re.search(b'name="csrf" value="([^"]+)"', page)[1].decode()
        before = hashes(tmp_path)
        status, _, page = request(port, '/source/propose', method='POST',
            body=urlencode(dict(id=record['source_id'],csrf=csrf,start=1)),
            content_type='application/x-www-form-urlencoded')
        assert status == 200 and b'Analyser le passage suivant' in page
        start = re.search(b'name="start" value="([^"]+)"', page)[1].decode()
        assert start == '2'
        status, _, page = request(port, '/source/propose', method='POST',
            body=urlencode(dict(id=record['source_id'],csrf=csrf,start=start)),
            content_type='application/x-www-form-urlencoded')
        assert status == 200 and b'Fin du document' in page
        assert b'Analyser le passage suivant' not in page
        assert starts == [1,2] and hashes(tmp_path) == before


def test_empty_paragraphs_hidden_but_source_numbers_preserved(tmp_path):
    from core.monitoring.sources import render_extraction
    _, record, _ = __import__('tests.test_source_ai', fromlist=['setup']).setup(tmp_path)
    page = render_extraction(record, dict(extractor='test', text_sha256='a'*64,
        paragraphs=['', 'Lina.', '   ', 'Plume.']),csrf='secret',ai_enabled=True)
    assert '<li value="1">' not in page and '<li value="3">' not in page
    assert '<li value="2">' in page and '<li value="4">' in page


def test_unsupported_ai_quote_has_readable_error_and_retry_link(tmp_path):
    import json
    from tests.test_source_ai import setup
    from core.sources.local_ai import LocalDetailAI
    _, record, _ = setup(tmp_path)
    class UnsupportedAI(LocalDetailAI):
        def _request(self, path, payload=None):
            if path == '/api/tags':
                return dict(models=[dict(name=self.model,digest='a'*64)])
            return dict(model=self.model,done=True,response=json.dumps(dict(details=[
                dict(detail='Invented detail',paragraph=1,quote='Invented quote') ])))
    with server(tmp_path, ai=UnsupportedAI(model='qwen3:0.6b')) as port:
        page=request(port,'/source/text?id='+record['source_id'])[2]
        csrf=re.search(b'name="csrf" value="([^"]+)"',page)[1].decode()
        before=hashes(tmp_path)
        status,_,page=request(port,'/source/propose',method='POST',
            body=urlencode(dict(id=record['source_id'],csrf=csrf,start=1)),
            content_type='application/x-www-form-urlencoded')
        assert status == 422
        assert 'citation exacte'.encode() in page and b'Revenir au texte' in page
        assert b'Invented quote' not in page and b'Invented detail' not in page
        assert hashes(tmp_path)==before


def test_busy_ai_has_readable_retryable_error_without_writes(tmp_path):
    from tests.test_source_ai import setup
    from core.sources.local_ai import LocalDetailAI, _inference
    _, record, _ = setup(tmp_path)
    with server(tmp_path, ai=LocalDetailAI(model='qwen3:0.6b')) as port:
        page=request(port,'/source/text?id='+record['source_id'])[2]
        csrf=re.search(b'name="csrf" value="([^"]+)"',page)[1].decode()
        before=hashes(tmp_path)
        assert _inference.acquire(blocking=False)
        try:
            status,_,page=request(port,'/source/propose',method='POST',
                body=urlencode(dict(id=record['source_id'],csrf=csrf,start=1)),
                content_type='application/x-www-form-urlencoded')
        finally:
            _inference.release()
        assert status==409 and 'analyse est déjà en cours'.encode() in page
        assert b'Revenir au texte' in page and hashes(tmp_path)==before


def test_extracted_text_pages_keep_original_numbers_and_put_analysis_first(tmp_path):
    from tests.test_source_library import add
    store = seed(tmp_path)
    content = '\n'.join(value for number in range(1,81) for value in [f'Paragraphe {number:03}', ''])
    record = add(store, content.encode(), original_name='pages.txt')['source']
    store.extract(record['source_id'])
    with server(tmp_path, ai=object()) as port:
        before = hashes(tmp_path)
        base='/source/text?id='+record['source_id']
        status,_,first=request(port,base)
        assert status==200 and first.count(b'<li value=')==40
        assert b'Paragraphe 001' in first and b'Paragraphe 041' not in first
        assert first.index(b'Proposer des d') < first.index(b'<ol>')
        status,_,second=request(port,base+'&page=2')
        assert status==200 and second.count(b'<li value=')==40
        assert b'<li value="81">' in second and b'Paragraphe 041' in second
        assert b'Paragraphe 001' not in second and b'Paragraphe 080' in second
        assert b'name="start" min="1"' in second and b'value="81"' in second
        for suffix in ['&page=0','&page=3','&page=2&page=2','&page=abc']:
            assert request(port,base+suffix)[0]==404
        assert hashes(tmp_path)==before


def test_public_csrf_token_cannot_sign_an_invented_ai_review(tmp_path):
    from tests.test_source_ai import setup, review
    from core.sources.validation import seal
    _, record, extracted = setup(tmp_path)
    with server(tmp_path) as port:
        page=request(port,'/sources')[2]
        csrf=re.search(b'name="csrf" value="([^"]+)"',page)[1].decode()
        forged=review(record,extracted)
        forged['model']='model-never-run'
        token=seal(forged,csrf.encode())
        before=hashes(tmp_path)
        status,_,_=request(port,'/source/accept',method='POST',
            body=urlencode(dict(csrf=csrf,review=token,detail='Invented model provenance')),
            content_type='application/x-www-form-urlencoded')
        assert status==400 and hashes(tmp_path)==before


def test_pending_source_is_visible_and_can_be_resumed_from_library(tmp_path, monkeypatch):
    import pytest
    from core.sources.store import SourceStore
    from tests.test_source_library import add
    store=seed(tmp_path)
    add(store,b'existing',original_name='existing.txt',title='Already published')
    def stop(stage):
        if stage=='after_staging':
            raise RuntimeError('interrupted')
    with monkeypatch.context() as patch:
        patch.setattr(SourceStore,'_checkpoint',staticmethod(stop))
        with pytest.raises(RuntimeError):
            add(store,b'pending data',original_name='pending.txt',title='Pending title',author='Moi')
    with server(tmp_path) as port:
        before=hashes(tmp_path)
        status,_,page=request(port,'/sources')
        assert status==200 and b'Already published' in page and b'Pending title' in page
        assert b'pending.txt' in page and b'Reprendre' in page
        assert hashes(tmp_path)==before
        csrf=re.search(b'name="csrf" value="([^"]+)"',page)[1].decode()
        status,_,page=request(port,'/sources',method='POST',
            body=multipart(csrf,data=b'pending data',name='pending.txt',title='Pending title'),
            content_type='multipart/form-data; boundary=BOUNDARY')
        assert status==200 and not list(store.directory.glob('.pending-*'))
        assert len(store.list())==2
        pending=next(r for r in store.list() if r['title']=='Pending title')
        assert pending['added_at']=='2026-10-03T13:00:00Z'


def test_invalid_extraction_stage_does_not_hide_other_published_sources(tmp_path):
    from tests.test_source_library import add
    from core.operations.readiness import check_readiness
    store=seed(tmp_path)
    first=add(store,b'healthy',original_name='healthy.txt',title='Healthy source')['source']
    second=add(store,b'other',original_name='other.txt',title='Interrupted source')['source']
    (store.directory/second['source_id']/'.extraction.json.abcd.tmp').write_text('{')
    with server(tmp_path) as port:
        before=hashes(tmp_path)
        status,_,page=request(port,'/sources')
        assert status==200 and b'Healthy source' in page
        assert 'Vérification nécessaire'.encode() in page
        assert request(port,'/source?id='+first['source_id'])[0]==200
        assert hashes(tmp_path)==before
        assert not check_readiness(tmp_path)['ready']
