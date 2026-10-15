# ==========================================================
# Projet      : Eidolon Memory Engine
# Organisation: Eidolon Core Technologies (ECT)
# Fichier     : tests/claude_memory_eval/test_rebuild_proof_probes_g235.py
# Description : Contre-vérification Claude de Q1 corrigé (G235) : preuve avant publication de la génération
# Standard    : Eidolon Presentation Standard v1
# ==========================================================
"""Probes of QdrantIndex.rebuild after 507fbb1, in-memory Qdrant, real Markdown. GPT's files unchanged."""
import threading
import time

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
    for i in range(4):
        backend.store(Memory(f"doc-{i}", content=f"texte {i}", revision=1))
    client = qdrant.QdrantClient(":memory:")
    calls = []

    def embed(text):
        calls.append(text)
        hook = embed.hook
        if hook:
            hook()
        return [1.0, 0.0]
    embed.hook = None
    index = QdrantIndex(client, "eidolon_claude_q1", embed=embed, dimensions=2, embedding_id="synthetic-v1",
                        create=True)
    yield root, backend, client, index, embed
    client.close()


def test_every_rebuilt_point_carries_the_proof_of_the_bytes_it_was_built_from(setup):
    root, _, _, index, _ = setup
    index.rebuild(root)
    reader = CanonicalReader(root)
    for i in range(4):
        _, digest = reader(f"doc-{i}")
        evidence = index.evidence_for(f"doc-{i}")
        assert (evidence.canonical_sha256, evidence.revision, evidence.generation) == (
            digest, 1, index.active_generation())


def test_a_canon_changed_during_rebuild_is_never_published(setup):
    """A non-cooperating write (same thread, so the reentrant lock lets it through) lands mid-rebuild."""
    root, backend, client, index, embed = setup
    index.rebuild(root)
    before = index.active_generation()
    done = []

    def change_once():
        if not done:
            done.append(1)
            backend.update("doc-3", Memory("doc-3", content="modifié", revision=2), previous_revision=1)
    embed.hook = change_once
    with pytest.raises(ValueError):
        index.rebuild(root)
    embed.hook = None
    assert index.active_generation() == before                    # the alias did not move
    assert index.evidence_for("doc-3").revision == 1               # readers still see the proven old state


def test_a_cooperating_writer_waits_for_the_rebuild_and_is_not_lost(setup):
    """Pinned trade-off: rebuild holds the canonical writer lock for its whole duration."""
    root, backend, _, index, embed = setup
    started, attempting, finished = threading.Event(), threading.Event(), []
    completed_while_encoding = []

    def slow():
        started.set()
        assert attempting.wait(5)
        time.sleep(0.05)
        completed_while_encoding.append(bool(finished))
    embed.hook = slow

    def writer():
        started.wait(5)
        attempting.set()
        backend.update("doc-0", Memory("doc-0", content="après", revision=2), previous_revision=1)
        finished.append(time.monotonic())
    thread = threading.Thread(target=writer)
    thread.start()
    index.rebuild(root)
    # G241: a writer may finish after lock release but before this thread runs.
    # Prove blocking while encoding, without comparing post-return timestamps.
    time.sleep(0.05)  # explicitly allow that valid scheduling interleaving
    thread.join(10)
    embed.hook = None
    assert finished and completed_while_encoding and not any(completed_while_encoding)
    assert CanonicalReader(root)("doc-0")[0].revision == 2
    assert index.evidence_for("doc-0").revision == 1              # the index catches up via the journal later
