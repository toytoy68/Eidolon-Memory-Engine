# ==========================================================
# Projet      : Eidolon Memory Engine
# Organisation: Eidolon Core Technologies (ECT)
# Fichier     : tests/qdrant_response_proxy.py
# Description : Drop one acknowledged response from an owned disposable test server.
# Standard    : Eidolon Presentation Standard v1
# ==========================================================
"""Test-only fixed-target loopback proxy; never accepts an upstream URL from HTTP."""
from contextlib import contextmanager
from http.client import HTTPConnection
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import socket
import threading
from urllib.parse import urlsplit


class ResponseLoss:
    def __init__(self, upstream, mode):
        if mode not in ('disconnect', 'timeout'):
            raise ValueError('invalid response-loss mode')
        self.upstream, self.mode = upstream, mode
        self.armed, self.dropped, self.acknowledged = False, 0, False
        self.release = threading.Event()
        self.url = None

    def client(self):
        from qdrant_client import QdrantClient
        return QdrantClient(url=self.url, headers={'api-key': self.upstream.key},
            timeout=0.5, check_compatibility=False, trust_env=False)


@contextmanager
def drop_point_response(upstream, *, mode):
    target = urlsplit(upstream.url)
    if target.scheme != 'http' or target.hostname != '127.0.0.1' or not target.port:
        raise ValueError('owned loopback server required')
    state = ResponseLoss(upstream, mode)

    class Handler(BaseHTTPRequestHandler):
        protocol_version = 'HTTP/1.1'

        def log_message(self, *args):
            pass  # No credentials or request payloads in CI output.

        def forward(self):
            size = int(self.headers.get('Content-Length', '0'))
            if not 0 <= size <= 2*1024*1024 or not self.path.startswith('/'):
                self.send_error(400)
                return
            body = self.rfile.read(size)
            connection = HTTPConnection('127.0.0.1', target.port, timeout=3)
            try:
                connection.request(self.command, self.path, body=body,
                    headers={'api-key': upstream.key, 'Content-Type': 'application/json',
                             'Content-Length': str(len(body))})
                response = connection.getresponse()
                payload = response.read(4*1024*1024+1)
                if len(payload) > 4*1024*1024:
                    raise ValueError('oversized test response')
                if (state.armed and self.command == 'PUT'
                        and urlsplit(self.path).path.endswith('/points') and response.status == 200):
                    state.armed = False
                    state.dropped += 1
                    state.acknowledged = json.loads(payload).get('result', {}).get('status') == 'completed'
                    if state.mode == 'timeout':
                        state.release.wait(timeout=3)  # client timeout is 0.5 s
                    self.close_connection = True
                    try:
                        self.connection.shutdown(socket.SHUT_RDWR)
                    except OSError:
                        pass  # The timed-out client may already have closed it.
                    return  # Never send the acknowledged response to the worker.
                self.send_response(response.status)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)
            except (BrokenPipeError, ConnectionResetError):
                self.close_connection = True
            finally:
                connection.close()

        do_GET = do_POST = do_PUT = do_DELETE = do_PATCH = forward

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    server.daemon_threads = True
    state.url = f'http://127.0.0.1:{server.server_port}'
    thread = threading.Thread(target=lambda: server.serve_forever(poll_interval=0.05), daemon=True)
    thread.start()
    try:
        yield state
    finally:
        state.release.set()
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
        if thread.is_alive():
            raise RuntimeError('owned response proxy did not stop')
