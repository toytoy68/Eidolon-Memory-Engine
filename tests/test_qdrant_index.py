# ==========================================================
# Projet      : Eidolon Memory Engine
# Organisation: Eidolon Core Technologies (ECT)
# Fichier     : tests/test_qdrant_index.py
# Description : Optional Qdrant adapter contract and failure scenarios.
# Standard    : Eidolon Presentation Standard v1
# ==========================================================
"""Run against local Qdrant or an explicitly selected disposable server."""
import hashlib
import os
import re
import uuid

import pytest

qdrant = pytest.importorskip("qdrant_client")
from qdrant_client import models
from core.backend.filesystem import FilesystemBackend
from core.backend.models import Memory
from core.indexing.qdrant_index import QdrantIndex
from tests.contracts.index_port_contract import IndexPortContract


def embed(text):
    # Synthetic transport fixture, NOT a semantic embedding model.
    result = [0.0] * 32
    for word in re.findall(r"\w+", text.lower()):
        result[hashlib.sha256(word.encode()).digest()[0] % 32] += 1
    return result


@pytest.fixture
def client():
    url = os.environ.get("EIDOLON_TEST_QDRANT_URL")
    c = qdrant.QdrantClient(url=url, timeout=3) if url else qdrant.QdrantClient(":memory:")
    yield c
    c.close()


@pytest.fixture
def index(client):
    name = "eidolon_test_" + uuid.uuid4().hex
    idx = QdrantIndex(client, name, embed=embed, dimensions=32,
                      embedding_id="synthetic-hash-v1", create=True)
    yield idx
    # Only collections belonging to this unique test instance are removed.
    client.update_collection_aliases([models.DeleteAliasOperation(
        delete_alias=models.DeleteAlias(alias_name=name))])
    for c in client.get_collections().collections:
        if c.name.startswith(name + "__"):
            client.delete_collection(c.name)


class TestQdrantContract(IndexPortContract):
    @pytest.fixture
    def index(self, request):
        return request.getfixturevalue("index")


def test_reopen_and_incremental_digest(index, client, tmp_path):
    p = tmp_path / "persistent"
    backend = FilesystemBackend(p, tmp_path / "history")
    backend.store(Memory("a", content="robotique"))
    index.rebuild(p)
    old = index.status()
    reopened = QdrantIndex(client, index.alias, embed=embed, dimensions=32,
                           embedding_id="synthetic-hash-v1")
    assert reopened.status() == old
    reopened.upsert(Memory("b", content="fibre"))
    assert index.status().source_digest is None
    assert index.status().documents == 2


@pytest.mark.parametrize("vector", [[1.0], [0.0] * 32, [float("nan")] * 32,
                                   [float("inf")] * 32, [True] * 32])
def test_invalid_vectors_do_not_mutate(index, vector):
    index.upsert(Memory("safe", content="hydraulique"))
    index.embed = lambda _: vector
    with pytest.raises(ValueError):
        index.upsert(Memory("invalid", content="hydraulique"))
    assert index.status().documents == 1


@pytest.mark.parametrize("dimensions,identity", [(16, "synthetic-hash-v1"), (32, "other-model")])
def test_incompatible_embedding_rejected(index, client, dimensions, identity):
    with pytest.raises(ValueError, match="embedding"):
        QdrantIndex(client, index.alias, embed=embed, dimensions=dimensions,
                    embedding_id=identity)


def test_rebuild_embedding_failure_preserves_alias(index, tmp_path):
    index.upsert(Memory("old", content="hydraulique"))
    before = index.status()
    p = tmp_path / "persistent"
    FilesystemBackend(p, tmp_path / "history").store(Memory("new", content="fibre"))
    original = index.embed
    index.embed = lambda _: (_ for _ in ()).throw(RuntimeError("embedding offline"))
    with pytest.raises(RuntimeError):
        index.rebuild(p)
    index.embed = original
    assert index.status() == before
    assert index.query("hydraulique")[0].information_id == "old"


def test_source_changes_during_embedding_not_published(index, tmp_path):
    index.upsert(Memory("old", content="hydraulique"))
    p = tmp_path / "persistent"
    FilesystemBackend(p, tmp_path / "history").store(Memory("new", content="fibre"))
    original = index.embed
    def changing(text):
        (p / "new.md").write_bytes((p / "new.md").read_bytes().replace(b"fibre", b"autre"))
        return original(text)
    index.embed = changing
    with pytest.raises(ValueError, match="changed"):
        index.rebuild(p)
    index.embed = original
    assert index.query("hydraulique")[0].information_id == "old"


def test_payload_contains_no_body(index, client):
    index.upsert(Memory("a", content="private secret text", metadata={"private": "never copy"}))
    points, _ = client.scroll(index.alias, limit=10, with_vectors=False)
    doc = next(p for p in points if p.payload.get("kind") == "information")
    assert set(doc.payload) == {"kind", "information_id", "revision"}
    assert "private" not in str(doc.payload)


def test_alias_switch_failure_preserves_old(index, client, tmp_path, monkeypatch):
    index.upsert(Memory("old", content="hydraulique"))
    p = tmp_path / "persistent"
    FilesystemBackend(p, tmp_path / "history").store(Memory("new", content="fibre"))
    with monkeypatch.context() as patch:
        patch.setattr(client, "update_collection_aliases", lambda *a, **k: (_ for _ in ()).throw(TimeoutError()))
        with pytest.raises(TimeoutError):
            index.rebuild(p)
    assert index.query("hydraulique")[0].information_id == "old"


def test_lost_alias_ack_keeps_published_generation(index, client, tmp_path, monkeypatch):
    index.upsert(Memory("old", content="hydraulique"))
    p = tmp_path / "persistent"
    FilesystemBackend(p, tmp_path / "history").store(Memory("new", content="fibre"))
    original = client.update_collection_aliases
    def applied_without_ack(*a, **k):
        original(*a, **k)
        raise TimeoutError("ack lost")
    with monkeypatch.context() as patch:
        patch.setattr(client, "update_collection_aliases", applied_without_ack)
        with pytest.raises(TimeoutError):
            index.rebuild(p)
    assert index.query("fibre")[0].information_id == "new"
    assert index.status().source_digest is not None


def test_mutation_failure_invalidates_digest(index, client, tmp_path, monkeypatch):
    p = tmp_path / "persistent"
    FilesystemBackend(p, tmp_path / "history").store(Memory("a", content="fibre"))
    index.rebuild(p)
    with monkeypatch.context() as patch:
        patch.setattr(client, "delete", lambda *a, **k: (_ for _ in ()).throw(TimeoutError()))
        with pytest.raises(TimeoutError):
            index.delete("a")
    assert index.status().source_digest is None
    assert index.status().documents == 1


def test_independent_scopes_do_not_mix(index, client):
    name = "eidolon_test_" + uuid.uuid4().hex
    other = QdrantIndex(client, name, embed=embed, dimensions=32,
                        embedding_id="synthetic-hash-v1", create=True)
    try:
        index.upsert(Memory("same", content="hydraulique"))
        other.upsert(Memory("same", content="fibre"))
        other.delete("same")
        assert index.status().documents == 1
        assert other.status().documents == 0
    finally:
        client.update_collection_aliases([models.DeleteAliasOperation(
            delete_alias=models.DeleteAlias(alias_name=name))])
        for c in client.get_collections().collections:
            if c.name.startswith(name + "__"):
                client.delete_collection(c.name)


@pytest.mark.parametrize("limit", [0, -1, True, 1.5, 1001])
def test_invalid_limits(index, limit):
    with pytest.raises(ValueError):
        index.query("fibre", limit=limit)


def test_empty_rebuild(index, tmp_path):
    index.upsert(Memory("a", content="fibre"))
    p = tmp_path / "persistent"
    p.mkdir()
    index.rebuild(p)
    assert index.status().documents == 0
    assert index.status().source_digest is not None
    assert index.query("fibre") == []


def test_worker_upsert_to_disposable_qdrant(index, tmp_path):
    """End-to-end on the in-memory Qdrant fixture; never a live alias."""
    from core.indexing.worker_canonical import CanonicalReader
    from core.indexing.worker_upsert import apply_upsert
    from core.indexing.reconcile_plan import Action
    root = tmp_path / "persistent"
    backend = FilesystemBackend(root, tmp_path / "history")
    backend.store(Memory("doc", content="robotique"))
    reader = CanonicalReader(root)
    canonical, digest = reader("doc")
    receipt = apply_upsert(
        Action("ENQUEUE_UPSERT", "doc", None, canonical.revision, "manifest"),
        read_canonical=reader, authorize=lambda profile, identity, operation: True,
        index=index, profile_id="owner", model_id="synthetic-hash-v1",
        expected_model_id="synthetic-hash-v1", expected_profile_id="owner",
        expected_sha256=digest)
    assert receipt.state == "ACKNOWLEDGED"
    assert index.status().documents == 1
    assert index.query("robotique")[0].information_id == "doc"
