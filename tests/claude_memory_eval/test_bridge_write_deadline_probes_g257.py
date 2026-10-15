# ==========================================================
# Projet      : Eidolon Memory Engine
# Organisation: Eidolon Core Technologies (ECT)
# Fichier     : tests/claude_memory_eval/test_bridge_write_deadline_probes_g257.py
# Description : Contre-revue G257 : délais de lecture, d'écriture et de rappel distingués (Claude, G256-8)
# Standard    : Eidolon Presentation Standard v1
# ==========================================================
"""Synthetic loopback only, disposable server. Distinct from Codex's G257 test, which stays untouched.

- the write deadline is its own budget, not what is left of the read deadline;
- a recall longer than the request deadline is neither cut nor answered with 408;
- the write is bounded close to one request_timeout, not "eventually";
- a blocked response does not retain the recall lock (proposal adopted in G259; original patch preserved).
"""
from dataclasses import dataclass
import json
import socket
import threading
import time

import pytest
from services import memory_bridge as bridge
from tests.test_memory_bridge_limits_g245 import TOKEN, REQUEST, capacity_released, request

BIG = 120 * 1024


@dataclass
class Bundle:
    data: str


class Recall:
    def __init__(self, sizes=(BIG,), delay=0.0):
        self.calls, self.sizes, self.delay = [], list(sizes), delay

    def recall(self, **kwargs):
        self.calls.append(kwargs)
        time.sleep(self.delay)
        return Bundle('x' * (self.sizes.pop(0) if self.sizes else 2))


class Run:
    """One server whose handler records when each response write starts and ends."""

    def __init__(self, recall, *, timeout, connections=2):
        self.events, self.lock = [], threading.Lock()
        run = self

        class Handler(bridge.make_handler(recall, TOKEN, request_timeout=timeout)):
            def setup(self):
                super().setup()
                self.connection.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 4096)

            def respond_bytes(self, code, data):
                start = time.monotonic()
                try:
                    return super().respond_bytes(code, data)
                finally:
                    with run.lock:
                        run.events.append((code, len(data), time.monotonic() - start))

        self.httpd = bridge.BoundedRecallServer(('127.0.0.1', 0), Handler, max_connections=connections,
                                                request_timeout=timeout)
        self.thread = threading.Thread(target=self.httpd.serve_forever, kwargs={'poll_interval': .01},
                                       daemon=True)

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *exc):
        self.httpd.shutdown()
        self.httpd.server_close()
        self.thread.join(2)
        assert not self.thread.is_alive()

    def client(self):
        c = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        c.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 1024)  # before connect: small window
        c.settimeout(3)
        c.connect(self.httpd.server_address)
        return c


def framed(body=None):
    body = json.dumps(REQUEST).encode() if body is None else body
    return (f'POST /v1/recall HTTP/1.0\r\nAuthorization: Bearer {TOKEN}\r\n'
            f'Content-Length: {len(body)}\r\n\r\n').encode(), body


def read_all(c):
    chunks = []
    while True:
        part = c.recv(65536)
        if not part:
            return b''.join(chunks)
        chunks.append(part)


def test_the_write_budget_is_not_the_leftover_of_the_read_budget():
    # The request uses ~80 % of the read deadline, then the client pauses before reading the answer.
    # With the leftover read budget as write timeout (~0.1 s), the 120 KiB answer would be cut.
    timeout = .5
    with Run(Recall(), timeout=timeout) as run:
        c = run.client()
        try:
            head, body = framed()
            c.sendall(head + body[:-2])
            time.sleep(timeout * .8)
            c.sendall(body[-2:-1])  # the server's next read starts now, with ~20 % of its budget left
            time.sleep(.02)
            c.sendall(body[-1:])
            time.sleep(timeout * .6)
            raw = read_all(c)
        finally:
            c.close()
        assert raw.startswith(b'HTTP/1.0 200'), raw[:40]
        assert len(raw.split(b'\r\n\r\n', 1)[1]) > 100 * 1024


def test_a_recall_longer_than_the_request_deadline_is_answered_not_timed_out():
    with Run(Recall(sizes=(2,), delay=.4), timeout=.25) as run:
        code, payload = request(run.httpd)
        assert code == 200 and json.loads(payload)['result'] == {'data': 'xx'}
        assert [e[0] for e in run.events] == [200]


@pytest.mark.parametrize('part', ['head', 'body'])
def test_a_trickled_request_is_cut_within_its_deadline_and_never_reaches_recall(part):
    recall = Recall()
    with Run(recall, timeout=.25) as run:
        c = run.client()
        try:
            head, body = framed()
            data = head[:40] if part == 'head' else head + body
            if part == 'body':
                c.sendall(head)  # a complete head at once, then the body byte by byte
            begin = time.monotonic()
            for n in range(0 if part == 'head' else len(head), len(data)):
                try:
                    c.sendall(data[n:n + 1])
                except OSError:
                    break  # the server already answered and closed
                time.sleep(.02)  # each byte resets no idle timer: one deadline for the whole request
            raw = read_all(c)
            elapsed = time.monotonic() - begin
        finally:
            c.close()
        # Head: the standard library closes without an answer. Body: do_POST answers 408.
        assert raw == b"" if part == "head" else raw.startswith(b"HTTP/1.0 408"), raw[:80]
        assert recall.calls == [] and elapsed < 1.5
        capacity_released(run.httpd)


@pytest.mark.parametrize('trickle', [False, True], ids=['no-reader', 'slow-reader'])
def test_the_blocked_write_ends_close_to_one_request_timeout(trickle):
    timeout = .3
    with Run(Recall(), timeout=timeout) as run:
        c = run.client()
        stop = threading.Event()
        try:
            c.sendall(b''.join(framed()))
            if trickle:
                def slowly():
                    while not stop.wait(.03):
                        try:
                            if not c.recv(16):
                                return
                        except OSError:
                            return
                threading.Thread(target=slowly, daemon=True).start()
            deadline = time.monotonic() + 3
            while not run.events and time.monotonic() < deadline:
                time.sleep(.01)
        finally:
            stop.set()
            c.close()
        (code, size, elapsed), = run.events
        assert code == 200 and size > 100 * 1024
        # sendall's timeout is a total duration (Python >= 3.5): a trickling reader cannot extend it.
        # Headers are a separate, small sendall; the bound is one timeout plus scheduling slack.
        assert timeout * .8 <= elapsed <= 2 * timeout + .2, elapsed
        capacity_released(run.httpd)
        assert request(run.httpd)[0] == 200


def test_a_blocked_write_does_not_hold_the_recall_lock():
    with Run(Recall(sizes=(BIG, 2)), timeout=.5, connections=2) as run:
        c = run.client()
        try:
            c.sendall(b''.join(framed()))
            time.sleep(.15)  # A's recall finished, its write is blocked
            code, _ = request(run.httpd)  # B is a normal client
        finally:
            c.close()
        assert code == 200  # before G259: 503 BUSY for up to request_timeout
