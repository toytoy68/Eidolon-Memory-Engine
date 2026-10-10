# ==========================================================
# Projet      : Eidolon Memory Engine
# Organisation: Eidolon Core Technologies (ECT)
# Fichier     : services/memory_bridge.py
# Description : Bridge de rappel local, authentifie et borne
# ==========================================================
"""Experimental loopback-only recall bridge; no write endpoints.

The canonical backend may create lock files during reads. Do not mount the
underlying filesystem read-only without validating the existing engine contract.
"""
from dataclasses import asdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import hmac
import json
import os
import threading

from core.backend.filesystem import FilesystemBackend
from core.retrieval.contextual import ContextualRecall

MAX_BODY = 4096
MAX_RESPONSE = 128 * 1024


def validate_request(value):
    if not isinstance(value, dict) or set(value) != {"query", "mode", "max_items", "max_chars", "max_item_chars"}:
        raise ValueError("invalid request fields")
    if not isinstance(value["query"], str) or not 1 <= len(value["query"]) <= 500:
        raise ValueError("invalid query")
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in value["query"]):
        raise ValueError("invalid query characters")
    if value["mode"] != "operational":
        raise ValueError("only operational recall is exposed")
    for key, low, high in (("max_items", 1, 5), ("max_chars", 1, 4000), ("max_item_chars", 1, 800)):
        if type(value[key]) is not int or not low <= value[key] <= high:
            raise ValueError("invalid limits")
    return value


def make_handler(recall, token):
    lock = threading.Lock()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):
            pass  # Never log private query strings or bearer credentials.

        def respond(self, code, payload):
            data = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_POST(self):
            if self.path != "/v1/recall":
                return self.respond(404, {"error": "NOT_FOUND"})
            authorization = self.headers.get("Authorization", "")
            if not hmac.compare_digest(authorization, "Bearer " + token):
                return self.respond(401, {"error": "UNAUTHORIZED"})
            try:
                length = int(self.headers.get("Content-Length", "-1"))
                if not 1 <= length <= MAX_BODY:
                    return self.respond(413, {"error": "INVALID_LENGTH"})
                request = validate_request(json.loads(self.rfile.read(length)))
            except (ValueError, UnicodeError, json.JSONDecodeError):
                return self.respond(400, {"error": "INVALID_REQUEST"})
            if not lock.acquire(blocking=False):
                return self.respond(503, {"error": "BUSY"})
            try:
                result = recall.recall(**request)
                payload = {"schema": "eidolon-memory-recall/1", "result": asdict(result)}
                if len(json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")) > MAX_RESPONSE:
                    return self.respond(503, {"error": "RESPONSE_TOO_LARGE"})
                return self.respond(200, payload)
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
    args = parser.parse_args()
    if not 1024 <= args.port <= 65535:
        parser.error("invalid port")
    token = os.environ.get("EIDOLON_MEMORY_BRIDGE_TOKEN", "")
    if len(token) < 32 or any(ord(c) < 33 or ord(c) > 126 for c in token):
        parser.error("EIDOLON_MEMORY_BRIDGE_TOKEN must be a nonempty strong printable secret (32+ chars)")
    root = args.root.resolve(strict=True)
    if not (root / "memory" / "persistent").is_dir() or not (root / "memory" / "history").is_dir():
        parser.error("canonical memory directories must exist")
    backend = FilesystemBackend(root / "memory" / "persistent", root / "memory" / "history")
    recall = ContextualRecall(backend)
    server = ThreadingHTTPServer(("127.0.0.1", args.port), make_handler(recall, token))
    server.daemon_threads = True
    server.serve_forever()


if __name__ == "__main__":
    main()
