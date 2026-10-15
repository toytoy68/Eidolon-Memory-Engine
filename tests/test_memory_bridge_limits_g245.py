# ==========================================================
# Projet      : Eidolon Memory Engine
# Organisation: Eidolon Core Technologies (ECT)
# Fichier     : tests/test_memory_bridge_limits_g245.py
# Description : Bounded HTTP transport for authenticated local memory recall.
# Standard    : Eidolon Presentation Standard v1
# ==========================================================
from contextlib import contextmanager
from dataclasses import dataclass
import json
import socket
import threading
import time

import pytest

from services import memory_bridge as bridge

TOKEN = 'synthetic-' + 'x' * 40
REQUEST = dict(query='power', mode='operational', max_items=5, max_chars=4000, max_item_chars=800)


class Recall:
    def __init__(self):
        self.calls = []
    def recall(self, **kwargs):
        self.calls.append(kwargs)
        @dataclass
        class Bundle:
            items: tuple = ()
        return Bundle()


@contextmanager
def server(recall=None, *, timeout=.2, connections=2):
    recall = Recall() if recall is None else recall
    httpd = bridge.BoundedRecallServer(('127.0.0.1', 0), bridge.make_handler(recall, TOKEN,
        request_timeout=timeout), max_connections=connections, request_timeout=timeout)
    thread = threading.Thread(target=httpd.serve_forever, kwargs={'poll_interval': .01}, daemon=True)
    thread.start()
    try:
        yield httpd, recall
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(2)
        assert not thread.is_alive()


def capacity_released(httpd):
    assert httpd._slots.acquire(timeout=1)
    httpd._slots.release()


def request(httpd, *, headers=(), body=None, length=None):
    body = json.dumps(REQUEST).encode() if body is None else body
    length = len(body) if length is None else length
    head = ['POST /v1/recall HTTP/1.0', 'Host: localhost', 'Authorization: Bearer ' + TOKEN,
            'Content-Length: ' + str(length), *headers, '', '']
    with socket.create_connection(httpd.server_address, timeout=2) as client:
        client.sendall('\r\n'.join(head).encode('latin-1') + body)
        chunks = []
        while True:
            part = client.recv(4096)
            if not part:
                break
            chunks.append(part)
    raw = b''.join(chunks)
    return int(raw.split(b' ', 2)[1]), raw.split(b'\r\n\r\n', 1)[1]


@pytest.mark.parametrize('headers', [('Content-Length: 1',), ('Transfer-Encoding: chunked',)])
def test_ambiguous_body_framing_is_rejected_without_recall(headers):
    with server() as (httpd, recall):
        code, body = request(httpd, headers=headers)
        assert code == 400
        assert json.loads(body) == {'error': 'INVALID_REQUEST'}
        assert recall.calls == []


@pytest.mark.parametrize('headers', [('Authorization: Bearer duplicate',), ('Authorization: Bearer é',)])
def test_duplicate_authorization_is_rejected_without_recall(headers):
    with server() as (httpd, recall):
        assert request(httpd, headers=headers)[0] == 401
        assert recall.calls == []


def test_non_ascii_authorization_returns_401_instead_of_crashing():
    with server() as (httpd, recall):
        with socket.create_connection(httpd.server_address, timeout=2) as client:
            client.sendall(b'POST /v1/recall HTTP/1.0\r\nAuthorization: Bearer \xe9\r\nContent-Length: 1\r\n\r\nx')
            assert b' 401 ' in client.recv(4096)
        assert recall.calls == []


@pytest.mark.parametrize('body', [
    b'{"query":"hidden","query":"power","mode":"operational","max_items":5,"max_chars":4000,"max_item_chars":800}',
    json.dumps({**REQUEST, 'query': '   '}).encode(),
    b'{"query":"power","mode":"operational","max_items":NaN,"max_chars":4000,"max_item_chars":800}',
])
def test_invalid_json_or_blank_query_is_a_client_error(body):
    with server() as (httpd, recall):
        assert request(httpd, body=body)[0] == 400
        assert recall.calls == []


def test_stalled_short_body_times_out_and_releases_capacity():
    with server(timeout=.1, connections=1) as (httpd, recall):
        code, body = request(httpd, body=b'{', length=100)
        assert code == 408 and json.loads(body) == {'error': 'REQUEST_TIMEOUT'}
        assert recall.calls == []
        capacity_released(httpd)
        assert request(httpd)[0] == 200
        assert len(recall.calls) == 1


def test_trickled_body_has_one_deadline_not_a_fresh_timeout_per_byte():
    with server(timeout=.15) as (httpd, recall):
        with socket.create_connection(httpd.server_address, timeout=2) as client:
            head = f'POST /v1/recall HTTP/1.0\r\nAuthorization: Bearer {TOKEN}\r\nContent-Length: 100\r\n\r\n'
            client.sendall(head.encode())
            started = time.monotonic()
            stop = threading.Event()
            def trickle():
                while not stop.wait(.03):
                    try:
                        client.sendall(b' ')
                    except OSError:
                        break
            writer = threading.Thread(target=trickle, daemon=True)
            writer.start()
            try:
                reply = client.recv(4096)
                assert b' 408 ' in reply
                assert time.monotonic() - started < 1.0
            finally:
                stop.set()
                writer.join(1)
        assert recall.calls == []


def test_connection_cap_refuses_extra_client_then_recovers():
    entered, release = threading.Event(), threading.Event()
    class Slow(Recall):
        def recall(self, **kwargs):
            entered.set()
            assert release.wait(2)
            return super().recall(**kwargs)
    slow = Slow()
    with server(slow, connections=1) as (httpd, recall):
        result = []
        first = threading.Thread(target=lambda: result.append(request(httpd)), daemon=True)
        first.start()
        try:
            assert entered.wait(1)
            with socket.create_connection(httpd.server_address, timeout=2) as extra:
                assert b' 503 ' in extra.recv(4096)
        finally:
            release.set()
            first.join(2)
        assert result[0][0] == 200
        capacity_released(httpd)
        assert request(httpd)[0] == 200
        assert len(recall.calls) == 2


@pytest.mark.parametrize('value', [float('nan'), float('inf'), object(), '\ud800'])
def test_non_json_recall_payload_is_sanitized(value):
    class Invalid:
        def recall(self, **kwargs):
            @dataclass
            class Bundle:
                data: object
            return Bundle(value)
    with server(Invalid()) as (httpd, _):
        code, body = request(httpd)
        assert code == 503 and json.loads(body) == {'error': 'RECALL_UNAVAILABLE'}
        assert TOKEN.encode() not in body


@pytest.mark.parametrize('value', [0, True, -1, float('nan'), float('inf'), 31])
def test_invalid_timeout_is_refused_before_serving(value):
    with pytest.raises(ValueError):
        bridge.make_handler(Recall(), TOKEN, request_timeout=value)


@pytest.mark.parametrize('token', ['', 'short', 'é' * 40, 'a' * 4097])
def test_invalid_token_is_refused_before_serving(token):
    with pytest.raises(ValueError):
        bridge.make_handler(Recall(), token)


def test_slow_headers_are_closed_at_the_same_request_deadline():
    with server(timeout=.12, connections=1) as (httpd, recall):
        with socket.create_connection(httpd.server_address, timeout=2) as client:
            client.sendall(b'POST /v1/recall HTTP/1.0\r\nX-Slow: ')
            stop = threading.Event()
            def trickle():
                while not stop.wait(.02):
                    try:
                        client.sendall(b'a')
                    except OSError:
                        break
            thread = threading.Thread(target=trickle, daemon=True)
            thread.start()
            started = time.monotonic()
            try:
                assert client.recv(4096) == b''
                assert time.monotonic() - started < 1
            finally:
                stop.set()
                thread.join(1)
        assert not recall.calls
        capacity_released(httpd)
        assert request(httpd)[0] == 200


def test_eof_before_declared_body_is_bad_request():
    with server() as (httpd, recall):
        with socket.create_connection(httpd.server_address, timeout=2) as client:
            header = f'POST /v1/recall HTTP/1.0\r\nAuthorization: Bearer {TOKEN}\r\nContent-Length: 50\r\n\r\n'
            client.sendall(header.encode() + b'{}')
            client.shutdown(socket.SHUT_WR)
            assert b' 400 ' in client.recv(4096)
        assert not recall.calls


@pytest.mark.parametrize('capacity', [0, True, -1, 33, 1.5])
def test_invalid_connection_budget_never_opens_listener(capacity):
    with pytest.raises(ValueError):
        bridge.BoundedRecallServer(('127.0.0.1', 0), bridge.make_handler(Recall(), TOKEN),
                                   max_connections=capacity)


def test_bridge_refuses_nonloopback_listener():
    with pytest.raises(ValueError):
        bridge.BoundedRecallServer(('0.0.0.0', 0), bridge.make_handler(Recall(), TOKEN))


def test_oversized_utf8_response_is_refused_and_lock_released():
    class Huge(Recall):
        def recall(self, **kwargs):
            if self.calls:
                return super().recall(**kwargs)
            self.calls.append(kwargs)
            @dataclass
            class Bundle:
                content: str = '🙂' * 40000
            return Bundle()
    with server(Huge()) as (httpd, _):
        code, body = request(httpd)
        assert code == 503 and json.loads(body) == {'error': 'RESPONSE_TOO_LARGE'}
        assert len(body) < bridge.MAX_RESPONSE
        capacity_released(httpd)
        assert request(httpd)[0] == 200


def test_deep_json_is_rejected_without_handler_crash():
    with server() as (httpd, recall):
        code, body = request(httpd, body=b'[' * 1200 + b'0' + b']' * 1200)
        assert code == 400 and json.loads(body) == {'error': 'INVALID_REQUEST'}
        assert not recall.calls


def test_decoder_recursion_failure_is_a_sanitized_client_error(monkeypatch):
    def exhausted(*args, **kwargs):
        raise RecursionError('private decoder internals')
    with server() as (httpd, recall):
        monkeypatch.setattr(bridge.json, 'loads', exhausted)
        code, body = request(httpd)
        assert code == 400 and b'INVALID_REQUEST' in body
        assert not recall.calls
