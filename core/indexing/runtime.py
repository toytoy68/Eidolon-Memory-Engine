# ==========================================================
# Projet      : Eidolon Memory Engine
# Organisation: Eidolon Core Technologies (ECT)
# Fichier     : core/indexing/runtime.py
# Description : Pinned local embeddings and explicit Qdrant runtime
# Standard    : Eidolon Presentation Standard v1
# ==========================================================
"""Explicit loopback runtime; no downloads, provisioning or remote hosts.

A descriptor identity binds model digest, dimensions and both preprocessing paths.
One request embeds one bounded input. Socket deadlines are per I/O; this is not
an overall inference wall-clock guarantee. The host owns alias scope and service
isolation. Reading configuration is offline; opening an existing index is not.
"""
from dataclasses import dataclass
from hashlib import sha256
import http.client
import json
import math
from pathlib import Path
import re

from core.runtime_json import read_json_snapshot
from core.storage_format import decode_json_value

SCHEMA = "eidolon-index-runtime/1"

@dataclass(frozen=True)
class IndexRuntime:
    alias: str
    model: str
    model_digest: str
    dimensions: int
    query_instruction: str
    ollama_port: int
    qdrant_port: int
    timeout_seconds: int
    max_input_chars: int
    num_ctx: int
    projection: str = "documents"

    def __post_init__(self):
        if type(self.projection) is not str or self.projection not in ("documents", "archive_passages"):
            raise ValueError("invalid projection")
        if type(self.alias) is not str or not re.fullmatch(r"eidolon_[a-z0-9_]{1,90}", self.alias):
            raise ValueError("invalid alias")
        if type(self.model) is not str or not re.fullmatch(r"[A-Za-z0-9_.:/-]{1,128}", self.model):
            raise ValueError("invalid model")
        if type(self.model_digest) is not str or not re.fullmatch(r"[0-9a-f]{64}", self.model_digest):
            raise ValueError("model digest required")
        if (type(self.query_instruction) is not str or len(self.query_instruction) > 1000
                or any(ord(c) < 32 for c in self.query_instruction)):
            raise ValueError("invalid instruction")
        for name, low, high in (("dimensions",1,4096), ("ollama_port",1024,65535),
                ("qdrant_port",1024,65535), ("timeout_seconds",1,30),
                ("max_input_chars",1,1000000), ("num_ctx",128,32768)):
            value = getattr(self, name)
            if type(value) is not int or not low <= value <= high:
                raise ValueError("invalid " + name)

    @property
    def embedding_id(self):
        # Endpoint, alias and timeout do not change the vector projection.
        payload = ["ollama-cpu-embed-v1", self.model, self.model_digest,
                   self.dimensions, self.query_instruction, self.num_ctx, False]
        return "ollama-cpu-v1:" + sha256(json.dumps(payload, ensure_ascii=True,
            separators=(",", ":")).encode()).hexdigest()


def load_runtime(path):
    path = Path(path).absolute()
    raw = read_json_snapshot(str(path.parent), path.name, max_bytes=8192)
    if raw.pop("schema", None) != SCHEMA or set(raw) != set(IndexRuntime.__dataclass_fields__):
        raise ValueError("invalid runtime schema or fields")
    return IndexRuntime(**raw)


class OllamaEmbedding:
    def __init__(self, config):
        if type(config) is not IndexRuntime:
            raise ValueError("validated runtime required")
        self.config = config

    def _request(self, method, path, payload=None):
        c = self.config
        connection = http.client.HTTPConnection("127.0.0.1", c.ollama_port, timeout=c.timeout_seconds)
        try:
            body = None if payload is None else json.dumps(payload, allow_nan=False).encode()
            connection.request(method, path, body, {"Content-Type": "application/json"})
            response = connection.getresponse()
            if response.status != 200:
                raise ValueError("embedding service refused request")
            raw = response.read(4 * 1024 * 1024 + 1)
            if len(raw) > 4 * 1024 * 1024:
                raise ValueError("embedding response budget")
            result = decode_json_value(raw.decode("utf-8"))
            if type(result) is not dict:
                raise ValueError("invalid embedding response")
            return result
        finally:
            connection.close()

    def verify_model(self):
        c = self.config
        models = self._request("GET", "/api/tags").get("models")
        if type(models) is not list:
            raise ValueError("invalid model inventory")
        matches = [m for m in models if type(m) is dict and m.get("name") == c.model]
        if len(matches) != 1 or matches[0].get("digest") != c.model_digest:
            raise ValueError("embedding model absent or changed; no automatic download")

    def __call__(self, text):
        return self.embed(text, query=False)

    def query(self, text):
        return self.embed(text, query=True)

    def embed(self, text, *, query):
        c = self.config
        if type(text) is not str or not text.strip() or len(text) > c.max_input_chars:
            raise ValueError("embedding input budget")
        if query and c.query_instruction:
            text = "Instruct: " + c.query_instruction + "\nQuery:" + text
        if len(text) > c.max_input_chars:
            raise ValueError("embedding formatted input budget")
        self.verify_model()
        result = self._request("POST", "/api/embed", {"model": c.model, "input": [text],
            "truncate": False, "keep_alive": "2m", "options": {
                "num_gpu": 0, "num_thread": 2, "num_ctx": c.num_ctx}})
        vectors = result.get("embeddings")
        if result.get("model") != c.model or type(vectors) is not list or len(vectors) != 1:
            raise ValueError("embedding response mismatch")
        vector = vectors[0]
        if (type(vector) is not list or len(vector) != c.dimensions
                or any(type(v) not in (int, float) or not math.isfinite(v) for v in vector)
                or not 0 < math.hypot(*vector) < float("inf")):
            raise ValueError("invalid embedding vector")
        self.verify_model()
        return vector


def open_index(config, *, create=False):
    from qdrant_client import QdrantClient
    from core.indexing.qdrant_index import QdrantIndex
    from core.indexing.qdrant_passages import QdrantPassageIndex
    embed = OllamaEmbedding(config)
    # No proxy discovery or redirects: fixed loopback service endpoints only.
    client = QdrantClient(url=f"http://127.0.0.1:{config.qdrant_port}",
                          timeout=config.timeout_seconds, trust_env=False)
    try:
        adapter = QdrantIndex if config.projection == "documents" else QdrantPassageIndex
        index = adapter(client, config.alias, embed=embed, query_embed=embed.query,
            dimensions=config.dimensions, embedding_id=config.embedding_id, create=create)
    except BaseException:
        client.close()
        raise
    return index


def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser(description="Explicit local derived-index operations")
    parser.add_argument("--config", type=Path, required=True)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("check-config")
    commands.add_parser("status")
    rebuild = commands.add_parser("rebuild")
    rebuild.add_argument("--persistent-root", type=Path, required=True)
    rebuild.add_argument("--stopped-copy", action="store_true", required=True)
    rebuild.add_argument("--create-alias", action="store_true")
    args = parser.parse_args(argv)
    index = None
    try:
        config = load_runtime(args.config)
        if args.command == "check-config":
            result = {"state": "CONFIG_VALID", "embedding_id": config.embedding_id,
                      "services_checked": False}
        else:
            index = open_index(config, create=getattr(args, "create_alias", False))
            if args.command == "rebuild":
                index.rebuild(args.persistent_root)
            from dataclasses import asdict
            result = {"state": "INDEX_OBSERVED", **asdict(index.status())}
        print(json.dumps(result, sort_keys=True))
        return 0
    except Exception:
        print(json.dumps({"state": "UNAVAILABLE", "effects": "UNKNOWN" if args.command == "rebuild" else "NONE"}))
        return 2
    finally:
        if index is not None:
            index.client.close()

if __name__ == "__main__":
    raise SystemExit(main())
