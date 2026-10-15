# ==========================================================
# Projet      : Eidolon Memory Engine
# Organisation: Eidolon Core Technologies (ECT)
# Fichier     : tests/test_bridge_recall_lock_g259.py
# Description : Network writes must not retain the computation lock, including errors.
# Standard    : Eidolon Presentation Standard v1
# ==========================================================
from dataclasses import dataclass
import json
import threading
import pytest
from services import memory_bridge as bridge
from tests.test_memory_bridge_limits_g245 import TOKEN, request


@pytest.mark.parametrize('outcome', ['ok', 'failure', 'oversize'])
def test_stalled_response_leaves_recall_available(outcome):
    entered, release = threading.Event(), threading.Event()
    calls, replies = [], []
    @dataclass
    class Result:
        data: str
    class Recall:
        def recall(self, **kwargs):
            calls.append(kwargs)
            if len(calls) == 1:
                if outcome == 'failure':
                    raise RuntimeError('synthetic private failure')
                if outcome == 'oversize':
                    return Result('x' * (bridge.MAX_RESPONSE + 1))
            return Result('ok')
    class Handler(bridge.make_handler(Recall(), TOKEN)):
        def respond_bytes(self, code, data):
            if not entered.is_set():
                entered.set()
                assert release.wait(3)
            return super().respond_bytes(code, data)
    httpd = bridge.BoundedRecallServer(('127.0.0.1', 0), Handler, max_connections=2)
    serving = threading.Thread(target=httpd.serve_forever, kwargs={'poll_interval': .01}, daemon=True)
    serving.start()
    first = threading.Thread(target=lambda: replies.append(request(httpd)), daemon=True)
    first.start()
    try:
        assert entered.wait(1)
        code, body = request(httpd)
        assert code == 200
        assert json.loads(body)['result'] == {'data': 'ok'}
        assert len(calls) == 2
    finally:
        release.set()
        first.join(2)
        httpd.shutdown()
        httpd.server_close()
        serving.join(2)
        assert not first.is_alive() and not serving.is_alive()
    expected = 200 if outcome == 'ok' else 503
    assert replies[0][0] == expected
    if outcome != 'ok':
        assert b'synthetic private failure' not in replies[0][1]
