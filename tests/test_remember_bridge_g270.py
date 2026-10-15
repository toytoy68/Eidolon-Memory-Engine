# ==========================================================
# Projet      : Eidolon Memory Engine
# Organisation: Eidolon Core Technologies (ECT)
# Fichier     : tests/test_remember_bridge_g270.py
# Description : Profile binding and distinct HTTP write permission
# Standard    : Eidolon Presentation Standard v1
# ==========================================================
import http.client
import json
import threading
import pytest
from core.backend.filesystem import FilesystemBackend
from core.information.remember import prepare
from services.memory_bridge import BoundedRecallServer, build_recall, make_handler
from services.profile_binding import binding, require_binding
from services.remember_bridge import RememberEndpoint


def test_binding_is_explicit_immutable_and_not_a_relabel(tmp_path):
    FilesystemBackend(tmp_path/'memory/persistent', tmp_path/'memory/history')
    assert binding(tmp_path,'alice')['state'] == 'NOT_PREPARED'
    with pytest.raises(ValueError): RememberEndpoint(tmp_path,'alice')
    assert binding(tmp_path,'alice',apply=True)['state'] == 'BOUND'
    assert binding(tmp_path,'alice',apply=True)['state'] == 'BOUND'
    with pytest.raises(ValueError): binding(tmp_path,'bob',apply=True)
    with pytest.raises(ValueError): RememberEndpoint(tmp_path,'bob')


def test_recall_credential_cannot_write_and_actor_is_server_bound(tmp_path):
    FilesystemBackend(tmp_path/'memory/persistent', tmp_path/'memory/history')
    binding(tmp_path,'alice',apply=True)
    handler = make_handler(build_recall(tmp_path),'r'*40, remember=RememberEndpoint(tmp_path,'alice'),
                           write_token='w'*40, profile_id='alice', profile_check=lambda: require_binding(tmp_path,'alice'))
    server = BoundedRecallServer(('127.0.0.1',0),handler)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    command={'schema':'eidolon-remember/1','request_id':'one','actor':'alice','timestamp':'2026-10-15T19:00:00+00:00','text':'Private explicit memory.'}
    def call(token, raw):
        connection=http.client.HTTPConnection('127.0.0.1',server.server_address[1],timeout=3)
        try:
            payload={'command':raw,'approved_sha256':prepare(raw)[2]}
            connection.request('POST','/v1/remember',json.dumps(payload),{'Authorization':'Bearer '+token,'Content-Type':'application/json'})
            response=connection.getresponse();return response.status,json.loads(response.read())
        finally:connection.close()
    try:
        assert call('r'*40,command)[0] == 401
        assert not list((tmp_path/'memory/persistent').glob('*.md'))
        assert call('w'*40,dict(command,actor='bob'))[0] == 503
        status,result=call('w'*40,command)
        assert status == 200 and result['profile_id'] == 'alice' and result['result']['state'] == 'COMMITTED'
        assert call('w'*40,command) == (status,result)
        assert len(list((tmp_path/'memory/persistent').glob('*.md'))) == 1
        (tmp_path/'profile-binding.json').write_text(json.dumps({'schema':'eidolon-memory-profile/1','profile_id':'bob'}))
        assert call('w'*40,dict(command,request_id='two'))[0] == 503
    finally:server.shutdown();server.server_close();thread.join()
