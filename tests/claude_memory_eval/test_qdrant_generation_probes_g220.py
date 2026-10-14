# ==========================================================
# Projet      : Eidolon Memory Engine
# Organisation: Eidolon Core Technologies (ECT)
# Fichier     : tests/claude_memory_eval/test_qdrant_generation_probes_g220.py
# Description : Claude G220-5 : générations Qdrant, bascule d'alias, provenance après reconstruction
# Standard    : Eidolon Presentation Standard v1
# ==========================================================
"""Probes of QdrantIndex generations with an in-memory client (no server, no network). GPT's files unchanged."""
import pytest

from core.backend.filesystem import FilesystemBackend
from core.backend.models import Memory
from core.indexing.qdrant_index import QdrantIndex
from core.indexing.worker_canonical import CanonicalReader

qdrant = pytest.importorskip("qdrant_client")


@pytest.fixture
def setup(tmp_path):
    root = tmp_path / "persistent"
    backend = FilesystemBackend(root, tmp_path / "history")
    for i in range(3):
        backend.store(Memory(f"doc-{i}", content=f"texte {i}", revision=1))
    client = qdrant.QdrantClient(":memory:")
    index = QdrantIndex(client, "eidolon_claude_gen", embed=lambda _: [1.0, 0.0], dimensions=2,
                        embedding_id="synthetic-v1", create=True)
    yield root, client, index
    client.close()


def _collections(client):
    return sorted(c.name for c in client.get_collections().collections)


def test_a_rebuild_switches_the_alias_and_keeps_the_old_generation(setup):
    """No automatic deletion: the previous generation survives the switch (retirement is a reviewed plan)."""
    root, client, index = setup
    before = index.active_generation()
    index.rebuild(root)
    after = index.active_generation()
    assert after != before and set(_collections(client)) == {before, after}
    assert index.status().documents == 3


def test_a_verified_upsert_racing_a_rebuild_is_never_reported_verified(setup):
    """The write lands in the old generation; read-back targets the new alias, so provenance cannot match."""
    root, client, index = setup
    memory = Memory("doc-0", content="texte 0", revision=1)
    _, digest = CanonicalReader(root)("doc-0")
    evidence = index.upsert_verified(memory, canonical_sha256=digest)
    index.rebuild(root)
    assert index.evidence_for("doc-0") != evidence


# G235: Q1 reproduced with --runxfail, then corrected; assertions unchanged.
def test_a_rebuilt_generation_keeps_verifiable_provenance(setup):
    root, client, index = setup
    index.rebuild(root)
    _, digest = CanonicalReader(root)("doc-0")
    evidence = index.evidence_for("doc-0")
    assert evidence is not None and evidence.canonical_sha256 == digest
    assert evidence.generation == index.active_generation()


@pytest.mark.xfail(strict=True, reason="Claude finding Q2 (G220, low): QdrantIndex still exposes public delete() "
                   "and provenance-less upsert(). No worker calls them today, but 'no automatic deletion' rests on "
                   "every future caller. Expected: remove them from the production adapter or guard them behind an "
                   "explicit reviewed-deletion API.")
def test_the_production_adapter_offers_no_unreviewed_deletion(setup):
    _, _, index = setup
    assert not hasattr(index, "delete")
