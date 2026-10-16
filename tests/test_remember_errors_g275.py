# ==========================================================
# Projet      : Eidolon Memory Engine
# Organisation: Eidolon Core Technologies (ECT)
# Fichier     : tests/test_remember_errors_g275.py
# Description : Validation before writes and honest unknown-effect HTTP failures
# Standard    : Eidolon Presentation Standard v1
# ==========================================================
import http.client
import json
import threading
import pytest
from core.backend.filesystem import FilesystemBackend
from core.information.remember import prepare
from services.memory_bridge import BoundedRecallServer, build_recall, make_handler
from services.profile_binding import binding
from services.remember_bridge import RememberEndpoint, RememberValidationError


def fixture(tmp_path):
    FilesystemBackend(tmp_path/'memory/persistent',tmp_path/'memory/history')
    binding(tmp_path,'alice',apply=True)
    endpoint=RememberEndpoint(tmp_path,'alice')
    command=dict(schema='eidolon-remember/1',request_id='one',actor='alice',timestamp='2026-10-16T07:00:00+00:00',text='Synthetic memory')
    return endpoint,dict(command=command,approved_sha256=prepare(command)[2])


@pytest.mark.parametrize('problem',['actor','digest','shape','timestamp'])
def test_validation_precedes_writer(tmp_path,monkeypatch,problem):
    endpoint,request=fixture(tmp_path)
    def never(*args,**kwargs):raise AssertionError('writer constructed for invalid input')
    monkeypatch.setattr('services.remember_bridge.FilesystemInformationWrites',never)
    if problem=='actor':request['command']['actor']='bob'
    elif problem=='digest':request['approved_sha256']='0'*64
    elif problem=='shape':request['command'].pop('text')
    else:request['command']['timestamp']='invalid'
    with pytest.raises(RememberValidationError):endpoint(request)
    assert not list((tmp_path/'memory/persistent').glob('*.md'))


def test_http_validation_is_not_confused_with_failure_after_write(tmp_path):
    endpoint,request=fixture(tmp_path)
    def committed_then_failed(raw):
        endpoint(raw)
        raise ValueError('private path must not leak')
    def call(remember,raw):
        server=BoundedRecallServer(('127.0.0.1',0),make_handler(build_recall(tmp_path),'r'*40,remember=remember,write_token='w'*40))
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        c=http.client.HTTPConnection('127.0.0.1',server.server_address[1],timeout=5)
        try:
            c.request('POST','/v1/remember',json.dumps(raw),{'Authorization':'Bearer '+'w'*40,'Content-Type':'application/json'})
            response=c.getresponse();return response.status,json.loads(response.read())
        finally:c.close();server.shutdown();server.server_close();thread.join()
    assert call(endpoint,dict(request,approved_sha256='0'*64))==(400,{'error':'REMEMBER_INVALID_REQUEST','effects':'NONE'})
    assert not list((tmp_path/'memory/persistent').glob('*.md'))
    assert call(committed_then_failed,request)==(503,{'error':'REMEMBER_UNAVAILABLE','effects':'UNKNOWN'})
    assert len(list((tmp_path/'memory/persistent').glob('*.md')))==1
    assert call(endpoint,request)[0]==200
    assert len(list((tmp_path/'memory/persistent').glob('*.md')))==1
