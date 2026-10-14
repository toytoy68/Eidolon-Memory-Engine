# ==========================================================
# Projet      : Eidolon Memory Engine
# Organisation: Eidolon Core Technologies (ECT)
# Fichier     : tests/test_worker_integrity.py
# Description : Adversarial checks for canonical reads and Qdrant receipts.
# Standard    : Eidolon Presentation Standard v1
# ==========================================================
from pathlib import Path
from contextlib import closing
import os

import pytest

from core.backend.filesystem import FilesystemBackend
from core.backend.models import Memory
from core.indexing.reconcile_plan import Action
from core.indexing.worker_canonical import CanonicalReader
from core.indexing.worker_upsert import apply_upsert


def canonical(tmp_path):
    root = tmp_path / "persistent"
    FilesystemBackend(root, tmp_path / "history").store(Memory("doc", content="source"))
    reader = CanonicalReader(root)
    memory, digest = reader("doc")
    return root, reader, memory, digest


def arguments(reader, memory, digest, index):
    return dict(action=Action("INDEX_UPSERT", "doc", 1, memory.revision, "test"),
                read_canonical=reader, authorize=lambda *args: True, index=index,
                profile_id="owner", expected_profile_id="owner",
                model_id="synthetic-v1", expected_model_id="synthetic-v1",
                expected_sha256=digest)


def test_public_worker_requires_canonical_lock_before_any_effect(tmp_path):
    root, reader, memory, digest = canonical(tmp_path)
    class Index:
        def upsert(self, memory):
            pytest.fail("unlocked write")
    with pytest.raises(ValueError, match="canonical_root"):
        apply_upsert(**arguments(reader, memory, digest, Index()))


def test_reader_uses_open_descriptor_not_a_checked_path(tmp_path, monkeypatch):
    root, reader, memory, digest = canonical(tmp_path)
    def unsafe_read(path):
        pytest.fail("separate path check and read permit substitution")
    monkeypatch.setattr(Path, "read_bytes", unsafe_read)
    assert reader("doc") == (memory, digest)


def test_same_revision_wrong_qdrant_digest_never_acknowledged(tmp_path, monkeypatch):
    qdrant = pytest.importorskip("qdrant_client")
    from core.indexing.qdrant_index import QdrantIndex
    root, reader, memory, digest = canonical(tmp_path)
    with closing(qdrant.QdrantClient(":memory:")) as client:
        index = QdrantIndex(client, "eidolon_integrity", embed=lambda _: [1., 0.],
                            dimensions=2, embedding_id="synthetic-v1", create=True)
        original = client.upsert
        def corrupt(collection_name, points, **kwargs):
            for point in points:
                if point.payload.get("kind") == "information":
                    point.payload["canonical_sha256"] = "0" * 64
            return original(collection_name, points=points, **kwargs)
        monkeypatch.setattr(client, "upsert", corrupt)
        result = apply_upsert(**arguments(reader, memory, digest, index), canonical_root=root)
        assert result.state == "UNVERIFIED"


def test_link_substituted_at_open_is_not_followed(tmp_path, monkeypatch):
    root, reader, memory, digest = canonical(tmp_path)
    outside = tmp_path / "outside.md"
    outside.write_text("not canonical")
    original = os.open
    def substitute(path, flags, *args, **kwargs):
        if path == "doc.md":
            (root / "doc.md").unlink()
            (root / "doc.md").symlink_to(outside)
        return original(path, flags, *args, **kwargs)
    monkeypatch.setattr(os, "open", substitute)
    with pytest.raises(ValueError, match="unsafe"):
        reader("doc")


def test_replaced_root_refused_even_with_same_document_bytes(tmp_path):
    root, reader, memory, digest = canonical(tmp_path)
    root.rename(tmp_path / "old-root")
    root.mkdir()
    (root / "doc.md").write_bytes((tmp_path / "old-root/doc.md").read_bytes())
    with pytest.raises(ValueError, match="root changed"):
        reader("doc")


def test_fifo_is_refused_without_waiting(tmp_path):
    root, reader, memory, digest = canonical(tmp_path)
    (root / "doc.md").unlink()
    os.mkfifo(root / "doc.md")
    with pytest.raises(ValueError, match="unsafe"):
        reader("doc")


@pytest.mark.parametrize("field,value", [
    ("embedding_id", "different-model"), ("generation", "different-generation"),
    ("canonical_sha256", None), ("revision", True),
])
def test_corrupt_provenance_cannot_produce_ack(tmp_path, monkeypatch, field, value):
    qdrant = pytest.importorskip("qdrant_client")
    from core.indexing.qdrant_index import QdrantIndex
    root, reader, memory, digest = canonical(tmp_path)
    with closing(qdrant.QdrantClient(":memory:")) as client:
        index = QdrantIndex(client, "eidolon_integrity", embed=lambda _: [1., 0.],
                            dimensions=2, embedding_id="synthetic-v1", create=True)
        original = client.upsert
        def corrupt(collection_name, points, **kwargs):
            for point in points:
                if point.payload.get("kind") == "information":
                    point.payload[field] = value
            return original(collection_name, points=points, **kwargs)
        monkeypatch.setattr(client, "upsert", corrupt)
        try:
            receipt = apply_upsert(**arguments(reader, memory, digest, index), canonical_root=root)
        except ValueError:
            return
        assert receipt.state == "UNVERIFIED"
