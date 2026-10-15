# ==========================================================
# Projet      : Eidolon Memory Engine
# Organisation: Eidolon Core Technologies (ECT)
# Fichier     : tests/claude_memory_eval/test_bridge_lock_probes_g259.py
# Description : Contre-revue G259 : verrou libéré avant l'écriture, calculs sérialisés, réponse figée (Claude, G258-1/2)
# Standard    : Eidolon Presentation Standard v1
# ==========================================================
"""Synthetic loopback only. Distinct from Codex's G259 tests, which stay untouched.

G258-1: during a blocked write a second recall is served; two recalls never compute at once; the
        connection capacity stays bounded; a client vanishing during the write frees everything.
G258-2: the response bytes are frozen under the lock; a provider that reuses and mutates one object
        cannot change what an earlier client receives.
"""
from dataclasses import dataclass, field
import json
import socket
import threading
import time

import pytest
from services import memory_bridge as bridge
from tests.test_memory_bridge_limits_g245 import TOKEN, REQUEST, capacity_released, request


@dataclass
class Result:
    data: object = field(default_factory=list)


class Server:
    """A server whose response writes can be held, one gate per response, in arrival order."""

    def __init__(self, recall, *, connections=2, hold_writes=0, timeout=3.0):
        self.gates = [threading.Event() for _ in range(hold_writes)]
        self.entered = [threading.Event() for _ in range(hold_writes)]
        self.writes, self.lock = [], threading.Lock()
        server = self

        class Handler(bridge.make_handler(recall, TOKEN, request_timeout=timeout)):
            def respond_bytes(self, code, data):
                with server.lock:
                    n = len(server.writes)
                    server.writes.append((code, bytes(data)))
                if n < len(server.gates):
                    server.entered[n].set()
                    assert server.gates[n].wait(5)
                return super().respond_bytes(code, data)

        self.httpd = bridge.BoundedRecallServer(('127.0.0.1', 0), Handler, max_connections=connections,
                                                request_timeout=timeout)
        self.thread = threading.Thread(target=self.httpd.serve_forever, kwargs={'poll_interval': .01},
                                       daemon=True)

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *exc):
        for gate in self.gates:
            gate.set()
        self.httpd.shutdown()
        self.httpd.server_close()
        self.thread.join(2)
        assert not self.thread.is_alive()

    def background(self, replies):
        t = threading.Thread(target=lambda: replies.append(request(self.httpd)), daemon=True)
        t.start()
        return t


class Counting:
    """Records the maximum number of recalls computing at the same time."""

    def __init__(self, delay=0.0, fail=False):
        self.active = self.peak = 0
        self.calls, self.delay, self.fail, self.guard = 0, delay, fail, threading.Lock()

    def recall(self, **kwargs):
        with self.guard:
            self.active += 1
            self.calls += 1
            self.peak = max(self.peak, self.active)
        try:
            time.sleep(self.delay)
            if self.fail:
                raise RuntimeError('synthetic private failure')
            return Result(['ok'])
        finally:
            with self.guard:
                self.active -= 1


@pytest.mark.parametrize('outcome', ['ok', 'failure', 'oversize'])
def test_two_blocked_writes_do_not_block_a_third_recall_but_capacity_does(outcome):
    class Provider(Counting):
        def recall(self, **kwargs):
            result = super().recall(**kwargs)
            if outcome == 'oversize' and self.calls <= 2:
                return Result(['x' * bridge.MAX_RESPONSE])
            if outcome == 'failure' and self.calls <= 2:
                raise RuntimeError('synthetic private failure')
            return result
    recall = Provider()
    replies = []
    with Server(recall, connections=2, hold_writes=2) as s:
        a = s.background(replies)
        assert s.entered[0].wait(2)
        b = s.background(replies)
        assert s.entered[1].wait(2)        # second recall computed while the first write is held
        assert recall.calls == 2
        code, body = request(s.httpd)       # third client: both connection slots are taken
        assert (code, json.loads(body)) == (503, {'error': 'BUSY'}) and recall.calls == 2
        s.gates[0].set()
        s.gates[1].set()
        a.join(3)
        b.join(3)
        expected = {'ok': 200, 'failure': 503, 'oversize': 503}[outcome]
        assert sorted(r[0] for r in replies) == [expected, expected]
        assert all(b'private' not in r[1] for r in replies)
        capacity_released(s.httpd)
        assert request(s.httpd)[0] == 200 and recall.calls == 3
    assert recall.peak == 1


def test_recalls_are_still_computed_one_at_a_time():
    recall = Counting(delay=.3)
    replies = []
    with Server(recall, connections=8) as s:
        threads = [s.background(replies) for _ in range(6)]
        for t in threads:
            t.join(5)
    codes = sorted(r[0] for r in replies)
    assert recall.peak == 1 and codes.count(200) == recall.calls >= 1
    assert set(codes) <= {200, 503} and codes.count(503) == 6 - recall.calls
    assert codes.count(503) >= 1  # a colliding recall is refused at once (BUSY), never queued


def test_a_client_vanishing_during_a_held_write_frees_its_slot_and_the_lock():
    recall = Counting()
    with Server(recall, connections=1, hold_writes=1) as s:
        client = socket.create_connection(s.httpd.server_address, timeout=2)
        body = json.dumps(REQUEST).encode()
        client.sendall(f'POST /v1/recall HTTP/1.0\r\nAuthorization: Bearer {TOKEN}\r\n'
                       f'Content-Length: {len(body)}\r\n\r\n'.encode() + body)
        assert s.entered[0].wait(2)
        client.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, b'\x01\x00\x00\x00\x00\x00\x00\x00')
        client.close()                       # reset, the held write will fail
        s.gates[0].set()
        capacity_released(s.httpd)
        assert request(s.httpd)[0] == 200 and recall.calls == 2


# --- G258-2: the response is frozen under the lock ------------------------------------------------

class Stall(list):
    """A list whose copy (made while the result is serialized) can be held once."""
    hold = None

    def __init__(self, *args):
        if Stall.hold is not None:
            gate, Stall.hold = Stall.hold, None
            gate[0].set()
            gate[1].wait(2)
        super().__init__(*args)


def test_a_provider_mutating_a_shared_object_cannot_change_an_earlier_response():
    shared = Stall(['first'])
    calls = []

    class Reusing:
        def recall(self, **kwargs):
            calls.append(1)
            if len(calls) > 1:
                shared[:] = ['second']       # the provider reuses and mutates its single object
            return Result(shared)

    entered, release = threading.Event(), threading.Event()
    Stall.hold = (entered, release)          # holds the FIRST serialization, wherever it happens
    replies = []
    with Server(Reusing(), connections=2) as s:
        first = s.background(replies)
        assert entered.wait(2)
        second = request(s.httpd)            # 503 BUSY while the first serializes under the lock
        release.set()
        first.join(3)
    assert json.loads(replies[0][1])['result'] == {'data': ['first']}, replies[0]
    assert second[0] in (200, 503)
    if second[0] == 200:
        assert json.loads(second[1])['result'] == {'data': ['second']}


def test_the_bytes_written_are_exactly_the_bytes_frozen_for_this_request():
    counter = iter(range(1000))

    class Distinct:
        def recall(self, **kwargs):
            return Result([f'answer-{next(counter)}'])
    replies = []
    with Server(Distinct(), connections=4, hold_writes=3) as s:
        threads = []
        for n in range(3):
            threads.append(s.background(replies))
            assert s.entered[n].wait(2)
        for gate in reversed(s.gates):       # release in reverse order
            gate.set()
        for t in threads:
            t.join(3)
        frozen = {data for _, data in s.writes}
    bodies = {r[1] for r in replies}
    assert len(bodies) == 3 and bodies == frozen  # each client got its own bytes, nothing mixed
