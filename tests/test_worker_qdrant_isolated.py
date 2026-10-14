"""Isolated worker -> in-memory Qdrant integration; synthetic vectors only."""
import uuid
import pytest

qdrant = pytest.importorskip("qdrant_client")
from core.backend.models import Memory
from core.indexing.qdrant_index import QdrantIndex
from core.indexing.reconcile_plan import Action
from core.indexing.worker_isolated import run_isolated_upsert


def test_worker_writes_only_to_explicit_disposable_alias():
    client = qdrant.QdrantClient(":memory:")
    alias = "eidolon_worker_test_" + uuid.uuid4().hex
    def embed(text):
        return [1.0, float(len(text) % 7 + 1)]
    index = QdrantIndex(client, alias, embed=embed, dimensions=2,
                        embedding_id="synthetic-worker-v1", create=True)
    action = Action("INDEX_UPSERT", "doc", 1, 1, "synthetic")
    calls = []
    def read(_):
        calls.append(1)
        return Memory("doc", revision=1, content="robotique"), "a" * 64
    try:
        result = run_isolated_upsert(
            action, index=index, read_canonical=read, authorize=lambda p, d: p == "owner",
            profile_id="owner", model_id="synthetic-worker-v1",
            expected_profile_id="owner", expected_model_id="synthetic-worker-v1",
            expected_sha256="a" * 64, disposable_test=True)
        assert result.state == "APPLIED_UNCONFIRMED"
        assert len(calls) == 2
        assert index.status().documents == 1
        assert [hit.information_id for hit in index.query("robotique")] == ["doc"]
    finally:
        client.close()
