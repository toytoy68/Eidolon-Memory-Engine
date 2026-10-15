# ==========================================================
# Projet      : Eidolon Memory Engine
# Organisation: Eidolon Core Technologies (ECT)
# Fichier     : services/memory_bridge.py
# Description : Bridge de rappel local, authentifie et borne
# Standard    : Eidolon Presentation Standard v1
# ==========================================================
"""Experimental loopback-only recall bridge; no write endpoints.

The canonical backend may create lock files during reads. Do not mount the
underlying filesystem read-only without validating the existing engine contract.
"""
from dataclasses import asdict
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import hmac
import json
import math
import re
import time
import os
import threading

from core.backend.filesystem import FilesystemBackend
from core.retrieval.contextual import ContextualRecall

MAX_BODY = 4096
MAX_RESPONSE = 128 * 1024


def validate_request(value):
    if not isinstance(value, dict) or set(value) != {"query", "mode", "max_items", "max_chars", "max_item_chars"}:
        raise ValueError("invalid request fields")
    if (not isinstance(value["query"], str) or not value["query"].strip()
            or not 1 <= len(value["query"]) <= 500):
        raise ValueError("invalid query")
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in value["query"]):
        raise ValueError("invalid query characters")
    if value["mode"] != "operational":
        raise ValueError("only operational recall is exposed")
    for key, low, high in (("max_items", 1, 5), ("max_chars", 1, 4000), ("max_item_chars", 1, 800)):
        if type(value[key]) is not int or not low <= value[key] <= high:
            raise ValueError("invalid limits")
    return value


def _timeout(value):
    if type(value) not in (int, float) or not math.isfinite(value) or not 0 < value <= 30:
        raise ValueError("invalid request timeout")
    return float(value)


class _DeadlineReader:
    """One deadline for request line, headers and body, including slow trickles."""
    def __init__(self, reader, connection, seconds):
        self.reader, self.connection = reader, connection
        self.deadline = time.monotonic() + seconds

    def read1(self, size):
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("request read deadline")
        self.connection.settimeout(remaining)
        return self.reader.read1(size)

    def readline(self, limit=-1):
        # BaseHTTPRequestHandler supplies bounded line sizes. read1 performs
        # at most one underlying read; an idle timeout cannot be reset forever.
        result = bytearray()
        while limit < 0 or len(result) < limit:
            part = self.read1(1)
            if not part:
                break
            result.extend(part)
            if part == b"\n":
                break
        return bytes(result)

    def close(self):
        self.reader.close()


class BoundedRecallServer(ThreadingHTTPServer):
    """Loopback server with finite accepted-handler capacity, no queued threads.

    A recall already executing is not forcibly killed by the transport deadline.
    Its adapter must enforce its own operation timeouts. Capacity stays occupied
    until that call returns; service availability is not promised during a hang.
    """
    daemon_threads = True

    def __init__(self, address, handler, *, max_connections=8, request_timeout=3.0):
        if (address[0] != "127.0.0.1" or type(max_connections) is not int
                or not 1 <= max_connections <= 32):
            raise ValueError("invalid local bridge capacity or address")
        self.request_timeout = _timeout(request_timeout)
        self._slots = threading.BoundedSemaphore(max_connections)
        super().__init__(address, handler)

    def process_request(self, request, client_address):
        if not self._slots.acquire(blocking=False):
            body = b'{"error":"BUSY"}'
            try:
                request.settimeout(self.request_timeout)
                request.sendall(b"HTTP/1.0 503 Service Unavailable\r\n"
                    b"Content-Type: application/json\r\nCache-Control: no-store\r\n"
                    b"Connection: close\r\nContent-Length: " + str(len(body)).encode()
                    + b"\r\n\r\n" + body)
            except OSError:
                pass
            finally:
                self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except BaseException:
            self._slots.release()
            raise

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self._slots.release()


def _unique_object(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("duplicate request key")
        value[key] = item
    return value


def _invalid_constant(value):
    raise ValueError("nonfinite request value")


def make_handler(recall, token, *, request_timeout=3.0):
    request_timeout = _timeout(request_timeout)
    if (type(token) is not str or not 32 <= len(token) <= 4096
            or any(ord(c) < 33 or ord(c) > 126 for c in token)
            or not callable(getattr(recall, "recall", None))):
        raise ValueError("invalid bridge credentials or recall provider")
    lock = threading.Lock()

    class Handler(BaseHTTPRequestHandler):
        def setup(self):
            super().setup()
            self.rfile = _DeadlineReader(self.rfile, self.connection, request_timeout)

        def log_message(self, fmt, *args):
            pass  # Never log private query strings or bearer credentials.

        def respond(self, code, payload):
            data = json.dumps(payload, ensure_ascii=False, allow_nan=False).encode("utf-8")
            return self.respond_bytes(code, data)

        def respond_bytes(self, code, data):
            self.close_connection = True
            self.connection.settimeout(request_timeout)
            try:
                self.send_response(code)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
            except OSError:
                pass  # A disconnected client cannot require a second response.

        def do_POST(self):
            if self.path != "/v1/recall":
                return self.respond(404, {"error": "NOT_FOUND"})
            authorizations = self.headers.get_all("Authorization", [])
            if (len(authorizations) != 1 or not authorizations[0].isascii()
                    or not hmac.compare_digest(authorizations[0], "Bearer " + token)):
                return self.respond(401, {"error": "UNAUTHORIZED"})
            try:
                lengths = self.headers.get_all("Content-Length", [])
                if self.headers.get_all("Transfer-Encoding", []) or len(lengths) > 1:
                    return self.respond(400, {"error": "INVALID_REQUEST"})
                if len(lengths) != 1 or not re.fullmatch(r"[0-9]{1,10}", lengths[0]):
                    return self.respond(413, {"error": "INVALID_LENGTH"})
                length = int(lengths[0])
                if not 1 <= length <= MAX_BODY:
                    return self.respond(413, {"error": "INVALID_LENGTH"})
                body = bytearray()
                while len(body) < length:
                    chunk = self.rfile.read1(length - len(body))
                    if not chunk:
                        return self.respond(400, {"error": "INVALID_REQUEST"})
                    body.extend(chunk)
                request = validate_request(json.loads(body, object_pairs_hook=_unique_object,
                                                      parse_constant=_invalid_constant))
            except TimeoutError:
                return self.respond(408, {"error": "REQUEST_TIMEOUT"})
            except (ValueError, UnicodeError, OSError, RecursionError):
                return self.respond(400, {"error": "INVALID_REQUEST"})
            if not lock.acquire(blocking=False):
                return self.respond(503, {"error": "BUSY"})
            try:
                result = recall.recall(**request, at=datetime.now(timezone.utc).isoformat())
                payload = {"schema": "eidolon-memory-recall/1", "result": asdict(result)}
                encoded = json.dumps(payload, ensure_ascii=False, allow_nan=False).encode("utf-8")
                if len(encoded) > MAX_RESPONSE:
                    return self.respond(503, {"error": "RESPONSE_TOO_LARGE"})
                return self.respond_bytes(200, encoded)
            except Exception:
                return self.respond(503, {"error": "RECALL_UNAVAILABLE"})
            finally:
                lock.release()

    return Handler


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--port", type=int, default=18765)
    parser.add_argument("--reranker-cache", type=Path, help="Optional offline CPU reranker cache")
    args = parser.parse_args()
    if not 1024 <= args.port <= 65535:
        parser.error("invalid port")
    token = os.environ.get("EIDOLON_MEMORY_BRIDGE_TOKEN", "")
    if not 32 <= len(token) <= 4096 or any(ord(c) < 33 or ord(c) > 126 for c in token):
        parser.error("EIDOLON_MEMORY_BRIDGE_TOKEN must be a nonempty strong printable secret (32 to 4096 chars)")
    root = args.root.resolve(strict=True)
    if not (root / "memory" / "persistent").is_dir() or not (root / "memory" / "history").is_dir():
        parser.error("canonical memory directories must exist")
    backend = FilesystemBackend(root / "memory" / "persistent", root / "memory" / "history")
    recall = ContextualRecall(backend)
    if args.reranker_cache is not None:
        from core.retrieval.reranked import RerankedRecall
        from sentence_transformers import CrossEncoder
        import torch
        torch.set_num_threads(2)
        encoder = CrossEncoder("cross-encoder/mmarco-mMiniLMv2-L12-H384-v1",
            device="cpu", cache_folder=str(args.reranker_cache),
            max_length=512, local_files_only=True)
        def score(query, texts):
            return encoder.predict([(query, text) for text in texts],
                batch_size=8, show_progress_bar=False).tolist() if texts else []
        recall = RerankedRecall(recall, score)
    server = BoundedRecallServer(("127.0.0.1", args.port), make_handler(recall, token))
    server.serve_forever()


if __name__ == "__main__":
    main()
