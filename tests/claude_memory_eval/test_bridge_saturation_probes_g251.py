# ==========================================================
# Projet      : Eidolon Memory Engine
# Organisation: Eidolon Core Technologies (ECT)
# Fichier     : tests/claude_memory_eval/test_bridge_saturation_probes_g251.py
# Description : Contre-revue Claude G245 : saturation du pont mémoire (rappel unique, fuite de capacité)
# Standard    : Eidolon Presentation Standard v1
# ==========================================================
"""Kill two mutants of services/memory_bridge.py that survive GPT's 40 bridge tests (local mutation, file
restored): the one-recall-at-a-time guard and the slot release when handler start-up fails. Loopback only."""
import socketserver
import threading
import time

from tests.test_memory_bridge_limits_g245 import Recall, capacity_released, request, server


def test_a_second_recall_while_one_hangs_is_refused_busy_at_once():
    entered, release = threading.Event(), threading.Event()

    class Hanging(Recall):
        def recall(self, **kwargs):
            entered.set()
            assert release.wait(5)
            return super().recall(**kwargs)
    with server(Hanging(), connections=2, timeout=1.0) as (httpd, recall):
        first = []
        thread = threading.Thread(target=lambda: first.append(request(httpd)), daemon=True)
        thread.start()
        try:
            assert entered.wait(2)
            started = time.monotonic()
            status, body = request(httpd)
            assert status == 503 and b'BUSY' in body
            assert time.monotonic() - started < 0.8                    # refused, not queued behind the hang
        finally:
            release.set()
            thread.join(5)
        assert first[0][0] == 200 and len(recall.calls) == 1
        capacity_released(httpd)


def test_a_failed_handler_start_gives_its_slot_back(monkeypatch):
    original = socketserver.ThreadingMixIn.process_request
    failures = [1]

    def fail_once(self, request_socket, client_address):
        if failures:
            failures.pop()
            raise RuntimeError("cannot start handler thread")
        return original(self, request_socket, client_address)
    monkeypatch.setattr(socketserver.ThreadingMixIn, "process_request", fail_once)
    with server(connections=1) as (httpd, recall):
        httpd.handle_error = lambda *a: None                            # quiet: the failure is expected
        try:
            request(httpd)
        except (OSError, IndexError, ValueError):
            pass                                                         # the first connection is dropped
        capacity_released(httpd)
        assert request(httpd)[0] == 200
