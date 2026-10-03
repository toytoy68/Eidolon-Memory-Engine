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
        assert b'<script>' not in page and b'&lt;script&gt;' in page
        identity = store.list()[0]['source_id']
        status, headers, original = request(port, '/source/original?id='+identity)
        assert status == 200 and original == DATA
        assert headers['Content-Type'] == 'application/octet-stream'
        assert headers['Content-Disposition'].startswith('attachment;')
        assert request(port, '/source/original?id='+identity, auth=False)[0] == 401
        assert request(port, '/source?id=../other')[0] == 404


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
