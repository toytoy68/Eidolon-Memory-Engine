# ==========================================================
# Projet      : Eidolon Memory Engine
# Organisation: Eidolon Core Technologies (ECT)
# Fichier     : tests/test_memory_bridge_write_deadline_g257.py
# Description : Real TCP backpressure must release the handler and recall lock.
# Standard    : Eidolon Presentation Standard v1
# ==========================================================
"""Synthetic loopback only. Small kernel buffers force a bounded response to block.

The writer records an actual socket timeout; a fast, fully buffered response
cannot accidentally qualify this test. No production response limit is raised.
"""
from dataclasses import dataclass
import json
import socket
import threading

import pytest
from services import memory_bridge as bridge
from tests.test_memory_bridge_limits_g245 import TOKEN, REQUEST, capacity_released, request


@pytest.mark.parametrize('trickle', [False, True], ids=['no-reader', 'slow-reader'])
def test_blocked_response_times_out_then_releases_capacity_and_recall(trickle):
    started, finished, timed_out, stop = (threading.Event() for _ in range(4))
    sizes, calls = [], []

    class Recall:
        def recall(self, **kwargs):
            calls.append(kwargs)
            @dataclass
            class Bundle:
                data: str
            return Bundle('x' * (120 * 1024) if len(calls) == 1 else 'ok')

    class Writer:
        def __init__(self, stream):
            self.stream = stream
        def __getattr__(self, name):
            return getattr(self.stream, name)
        def write(self, data):
            try:
                return self.stream.write(data)
            except TimeoutError:
                timed_out.set()
                raise

    class Handler(bridge.make_handler(Recall(), TOKEN, request_timeout=.25)):
        def setup(self):
            super().setup()
            self.connection.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 4096)
            self.wfile = Writer(self.wfile)
        def respond_bytes(self, code, data):
            sizes.append(len(data))
            started.set()
            try:
                return super().respond_bytes(code, data)
            finally:
                finished.set()

    httpd = bridge.BoundedRecallServer(('127.0.0.1', 0), Handler,
                                       max_connections=1, request_timeout=.25)
    serving = threading.Thread(target=httpd.serve_forever, kwargs={'poll_interval': .01}, daemon=True)
    serving.start()
    client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    reader = None
    try:
        # Set before connect, so TCP negotiates the small receive window.
        client.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 1024)
        client.settimeout(2)
        client.connect(httpd.server_address)
        body = json.dumps(REQUEST).encode()
        head = (f'POST /v1/recall HTTP/1.0\r\nAuthorization: Bearer {TOKEN}\r\n'
                f'Content-Length: {len(body)}\r\n\r\n').encode()
        client.sendall(head + body)
        assert started.wait(2)
        if trickle:
            def read_slowly():
                while not stop.wait(.03):
                    try:
                        if not client.recv(16):
                            break
                    except OSError:
                        break
            reader = threading.Thread(target=read_slowly, daemon=True)
            reader.start()
        assert finished.wait(2), 'response write did not respect its transport timeout'
        assert timed_out.is_set(), 'fixture did not create real socket backpressure'
        assert 100 * 1024 < sizes[0] <= bridge.MAX_RESPONSE
        capacity_released(httpd)
        assert request(httpd)[0] == 200  # handler slot AND recall lock available
        assert len(calls) == 2
    finally:
        stop.set()
        client.close()  # also releases a deliberately unbounded mutant
        if reader is not None:
            reader.join(2)
            assert not reader.is_alive()
        httpd.shutdown()
        httpd.server_close()
        serving.join(2)
        assert not serving.is_alive()
