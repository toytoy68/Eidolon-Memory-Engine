# ==========================================================
# Projet      : Eidolon Memory Engine
# Organisation: Eidolon Core Technologies (ECT)
# Fichier     : tests/claude_memory_eval/test_bridge_transport_probes_g252.py
# Description : Contre-revue Claude G252-5 : déconnexion pendant la réponse, erreurs sans fuite, rappel distinct
# Standard    : Eidolon Presentation Standard v1
# ==========================================================
"""Disposable loopback server only (GPT's helpers); synthetic token and queries."""
import json
import socket
import threading
import time

from tests.test_memory_bridge_limits_g245 import REQUEST, TOKEN, Recall, capacity_released, request, server

SECRET_QUERY = 'requête-privée-' + 'z' * 20


def test_a_client_vanishing_before_the_response_frees_the_slot_and_the_server_survives():
    entered, release = threading.Event(), threading.Event()

    class Slow(Recall):
        def recall(self, **kwargs):
            entered.set()
            assert release.wait(5)
            return super().recall(**kwargs)
    with server(Slow(), connections=1, timeout=0.5) as (httpd, recall):
        body = json.dumps(REQUEST).encode()
        head = (f'POST /v1/recall HTTP/1.0\r\nHost: localhost\r\nAuthorization: Bearer {TOKEN}\r\n'
                f'Content-Length: {len(body)}\r\n\r\n').encode()
        client = socket.create_connection(httpd.server_address, timeout=2)
        client.sendall(head + body)
        assert entered.wait(2)
        client.close()                                    # gone while the recall is still running
        release.set()
        time.sleep(0.2)
        capacity_released(httpd)
        assert request(httpd)[0] == 200


def test_errors_never_echo_the_token_the_query_or_the_failure_text():
    class Failing(Recall):
        def recall(self, **kwargs):
            raise RuntimeError('internal failure about ' + kwargs['query'] + ' ' + TOKEN)
    with server(Failing()) as (httpd, recall):
        cases = [dict(), dict(headers=('Authorization: Bearer wrong',)),
                 dict(body=b'{"query": "' + SECRET_QUERY.encode() + b'"'),       # malformed JSON
                 dict(body=json.dumps(dict(REQUEST, query=SECRET_QUERY)).encode())]
        for case in cases:
            status, payload = request(httpd, **case)
            text = payload.decode('utf-8', 'replace')
            assert status >= 400
            assert TOKEN not in text and SECRET_QUERY not in text and 'internal failure' not in text


def test_the_read_deadline_does_not_cut_a_slow_recall_already_running():
    """Transport deadlines bound the request read, not the recall itself (documented contract)."""
    class SlowButFine(Recall):
        def recall(self, **kwargs):
            time.sleep(0.4)                               # longer than the 0.2 s request deadline
            return super().recall(**kwargs)
    with server(SlowButFine(), timeout=0.2) as (httpd, recall):
        assert request(httpd)[0] == 200 and len(recall.calls) == 1
