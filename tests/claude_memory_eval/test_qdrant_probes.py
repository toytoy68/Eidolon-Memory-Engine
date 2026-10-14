# ==========================================================
# Projet      : Eidolon Memory Engine
# Organisation: Eidolon Core Technologies (ECT)
# Fichier     : tests/claude_memory_eval/test_qdrant_probes.py
# Description : Contre-revue Claude de l'adaptateur Qdrant G179 : reprise, changement de modèle, péremption, empreinte (G178 tâche 4)
# Standard    : Eidolon Presentation Standard v1
# ==========================================================
"""Probes OUTSIDE Codex's reserved files (qdrant_index.py, test_qdrant_index.py are not modified).

Original strict xfails are resolved in G180: new-alias migration, visible snapshot
freshness, and removal of the per-text fingerprint. The original review remains archived in the patch. Local Qdrant (":memory:") and a SYNTHETIC hashing embedding: no semantic quality is measured here.
"""
from hashlib import sha256
import re
import os
import uuid

import pytest

qdrant = pytest.importorskip("qdrant_client")
from qdrant_client import models                              # noqa: E402
from core.backend.filesystem import FilesystemBackend          # noqa: E402
from core.backend.models import Memory                         # noqa: E402
from core.indexing.qdrant_index import QdrantIndex             # noqa: E402


def embed(text):
    result = [0.0] * 16
    for word in re.findall(r"\w+", text.lower()):
        result[sha256(word.encode()).digest()[0] % 16] += 1
    return result or [1.0]


@pytest.fixture
def client():
    url = os.environ.get("EIDOLON_TEST_QDRANT_URL")
    c = qdrant.QdrantClient(url=url, timeout=3) if url else qdrant.QdrantClient(":memory:")
    yield c
    c.close()


def make(client, alias=None, *, embedding_id="synthetic-hash-v1", create=True):
    return QdrantIndex(client, alias or "eidolon_probe_" + uuid.uuid4().hex[:12], embed=embed, dimensions=16,
                       embedding_id=embedding_id, create=create)


def corpus(tmp_path, items):
    root = tmp_path / "persistent"
    backend = FilesystemBackend(root, tmp_path / "history")
    for identity, text in items:
        backend.store(Memory(identity, content=text))
    return root


def collections(client, alias):
    return sorted(c.name for c in client.get_collections().collections if c.name.startswith(alias + "__"))


# --- Ce qui est déjà correct ---------------------------------------------------------------------------

def test_failed_rebuild_keeps_the_served_generation_and_leaves_one_orphan(client, tmp_path):
    index = make(client)
    index.rebuild(corpus(tmp_path / "a", [("a", "robotique durable")]))
    before = index.status()
    served = collections(client, index.alias)
    index.embed = lambda _: [float("nan")] * 16                   # the model fails during the next rebuild
    with pytest.raises(ValueError):
        index.rebuild(corpus(tmp_path / "b", [("b", "fibre optique")]))
    index.embed = embed
    assert index.status() == before                               # alias untouched, old answers still served
    assert [h.information_id for h in index.query("robotique")] == ["a"]
    assert len(collections(client, index.alias)) == len(served) + 1   # documented: no purge, orphan kept


def test_hits_never_carry_content(client, tmp_path):
    index = make(client)
    index.rebuild(corpus(tmp_path, [("secret", "le code du portail est 4831")]))
    hit = index.query("portail")[0]
    assert "4831" not in repr(hit) and hit.ranking["canonical_revalidation_required"] is True


# --- Écarts relevés (xfail strict : doivent devenir verts quand ils seront traités) ---------------------

def test_alias_to_vanished_collection_can_be_recreated_explicitly(client, tmp_path):
    """Q1 checked: deleting the served collection also drops its alias (local mode), so an explicit
    create=True rebuilds a fresh generation. To confirm against the real 1.15.4 server (G179)."""
    index = make(client)
    index.rebuild(corpus(tmp_path, [("a", "robotique")]))
    for name in collections(client, index.alias):                # operator error, partial restore, disk loss
        client.delete_collection(name)
    with pytest.raises(ValueError):
        make(client, index.alias, create=False)                  # never silently recreated
    recovered = make(client, index.alias, create=True)
    recovered.rebuild(corpus(tmp_path / "again", [("a", "robotique")]))
    assert [h.information_id for h in recovered.query("robotique")] == ["a"]


def test_model_change_has_an_explicit_migration(client, tmp_path):
    index = make(client)
    index.rebuild(corpus(tmp_path, [("a", "robotique")]))
    # G180: migration is explicit through a NEW alias; the old model remains usable.
    with pytest.raises(ValueError, match="embedding"):
        make(client, index.alias, embedding_id="synthetic-hash-v2", create=False)
    upgraded = make(client, embedding_id="synthetic-hash-v2", create=True)
    upgraded.rebuild(corpus(tmp_path / "v2", [("a", "robotique")]))
    assert upgraded.alias != index.alias
    assert upgraded.status().source_digest is not None
    assert index.query("robotique")[0].ranking["embedding_id"] == "synthetic-hash-v1"
    assert upgraded.query("robotique")[0].ranking["embedding_id"] == "synthetic-hash-v2"


def test_stale_index_is_visible_in_every_hit(client, tmp_path):
    index = make(client)
    index.rebuild(corpus(tmp_path, [("a", "robotique")]))
    index.upsert(Memory("b", content="robotique avancée"))       # incremental write: digest becomes None
    assert index.status().source_digest is None
    hit = index.query("robotique")[0]
    assert hit.ranking.get("source_digest", "missing") is None or hit.ranking.get("index_stale") is True


def test_text_fingerprint_is_not_a_plain_hash(client, tmp_path):
    secret = "le code du portail est 4831"
    index = make(client)
    index.rebuild(corpus(tmp_path, [("secret", secret)]))
    # G235: the private rebuilt point carries the full canonical file digest,
    # like verified upserts since G229; never a hash of the bare secret text.
    hit = index.query("portail")[0]
    assert "text_sha256" not in hit.ranking
    points, _ = client.scroll(index.alias, limit=10, with_vectors=False)
    payload = next(p.payload for p in points if p.payload.get("kind") == "information")
    assert set(payload) == {"kind", "information_id", "revision", "canonical_sha256",
                            "embedding_id", "generation", "projection_id"}
    from core.indexing.worker_canonical import CanonicalReader
    _, digest = CanonicalReader(tmp_path / "persistent")("secret")
    assert payload["canonical_sha256"] == digest
    assert secret not in repr(payload)
    assert sha256(secret.encode()).hexdigest() not in repr(payload)
    assert sha256(secret.encode()).hexdigest() not in repr(hit)
