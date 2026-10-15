# ==========================================================
# Projet      : Eidolon Memory Engine
# Organisation: Eidolon Core Technologies (ECT)
# Fichier     : services/memory_bridge.py
# Description : Bridge de rappel local, authentifie et borne
# Standard    : Eidolon Presentation Standard v1
# ==========================================================
"""Experimental loopback-only recall bridge; no write endpoints.

The default backend may create lock files during reads. --read-only-storage
opens existing lock inodes without writing, on Linux local storage only. All
canonical directories and locks must be prepared before starting this mode.
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
from core.persistence import has_symlink_component, require_read_only_lock_support, RepositoryBusy
from core.backend.errors import InvalidMemory
from core.operations.readiness import check_readiness

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
                    code, encoded = 503, b'{"error": "RESPONSE_TOO_LARGE"}'
                else:
                    code = 200
            except Exception:
                code, encoded = 503, b'{"error": "RECALL_UNAVAILABLE"}'
            finally:
                lock.release()
            # Freeze the bounded response under the recall lock, then send it
            # outside: a slow reader must not serialize unrelated recalls.
            return self.respond_bytes(code, encoded)

    return Handler


def build_recall(root, *, read_only_storage=False):
    """Construct the canonical reader without provisioning in read-only mode.

    This does not restrict backend write methods: mount/UID permissions must
    enforce the deployment boundary. Model caches are configured separately.
    """
    if type(read_only_storage) is not bool:
        raise ValueError("read_only_storage must be boolean")
    root = Path(root)
    if has_symlink_component(root):
        raise ValueError("canonical root contains a symlink")
    backend = FilesystemBackend(root / "memory" / "persistent", root / "memory" / "history",
                                create_directories=not read_only_storage)
    recall = ContextualRecall(backend, read_only_locks=read_only_storage)
    if read_only_storage:
        # Fail before binding the server; revalidated on every recall as well.
        with recall.storage_snapshot(blocking=False):
            pass
    return recall


STORAGE_CHECK_EXIT = {'READY': 0, 'BLOCKED': 2, 'BUSY': 3, 'UNAVAILABLE': 4,
                      'UNSUPPORTED': 5, 'ERROR': 6}


def check_storage(root):
    """Inspect existing storage without provisioning, model loading or network.

    Lock acquisition is nonblocking; the canonical readiness scan has no global
    wall-clock budget. Output deliberately excludes paths, IDs and exceptions.
    A READY result is a point-in-time storage check, not deployment approval.
    """
    result = {'schema': 'eidolon-memory-storage-check/1',
              'scope': 'canonical_storage_only', 'state': 'ERROR',
              'read_only_locks': True, 'issues': None, 'warnings': None}
    try:
        require_read_only_lock_support()
        recall = build_recall(root, read_only_storage=True)
        with recall.storage_snapshot(blocking=False):
            report = check_readiness(recall.root)
            result.update(state='READY' if report['ready'] else 'BLOCKED',
                          issues=len(report['issues']), warnings=len(report['warnings']))
    except RepositoryBusy:
        result['state'] = 'BUSY'
    except NotImplementedError:
        result['state'] = 'UNSUPPORTED'
    except (OSError, ValueError, TypeError, InvalidMemory):
        result['state'] = 'UNAVAILABLE'
    except Exception:
        # Unexpected failures are explicit, without disclosing private records.
        result['state'] = 'ERROR'
    return result


def main():
    import argparse
    import sys

    # Recognize diagnostic intent before parsing: required/typed argument errors
    # occur before Namespace exists. Preserve argparse's unique long abbreviations.
    tokens = sys.argv[1:]
    if "--" in tokens:
        tokens = tokens[:tokens.index("--")]
    diagnostic = any(token.startswith("--") and len(token) > 2
                     and "--check-storage".startswith(token.partition("=")[0])
                     for token in tokens)

    class BridgeParser(argparse.ArgumentParser):
        def error(self, message):
            if diagnostic:
                self.print_usage(sys.stderr)
                self.exit(64, f"{self.prog}: error: {message}\n")
            super().error(message)

    parser = BridgeParser()
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--port", type=int)
    parser.add_argument("--reranker-cache", type=Path, help="Optional offline CPU reranker cache")
    parser.add_argument("--read-only-storage", action="store_true",
                        help="Linux local storage: require existing directories and lock files; never provision them")
    parser.add_argument("--check-storage", action="store_true",
                        help="Print a read-only canonical storage diagnostic as JSON and exit; no token/model/network")
    args = parser.parse_args()
    if args.check_storage:
        if args.port is not None or args.reranker_cache is not None:
            parser.error("--check-storage cannot be combined with --port or --reranker-cache")
        result = check_storage(args.root)
        print(json.dumps(result, ensure_ascii=True, sort_keys=True))
        return STORAGE_CHECK_EXIT[result['state']]
    if args.port is None:
        args.port = 18765
    if not 1024 <= args.port <= 65535:
        parser.error("invalid port")
    token = os.environ.get("EIDOLON_MEMORY_BRIDGE_TOKEN", "")
    if not 32 <= len(token) <= 4096 or any(ord(c) < 33 or ord(c) > 126 for c in token):
        parser.error("EIDOLON_MEMORY_BRIDGE_TOKEN must be a nonempty strong printable secret (32 to 4096 chars)")
    if has_symlink_component(args.root):
        parser.error("canonical root contains a symlink")
    root = args.root.resolve(strict=True)
    if not (root / "memory" / "persistent").is_dir() or not (root / "memory" / "history").is_dir():
        parser.error("canonical memory directories must exist")
    try:
        recall = build_recall(root, read_only_storage=args.read_only_storage)
    except (OSError, ValueError, NotImplementedError):
        parser.error("canonical storage unavailable; check existing directories, stable locks and platform support")
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
    raise SystemExit(main())
