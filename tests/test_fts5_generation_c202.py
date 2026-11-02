"""C202 generation rotation safety checks."""
from core.backend.filesystem import FilesystemBackend
from core.backend.models import Memory
from core.indexing.fts5_verified_experimental import VerifiedSqliteFts5Index
from core.indexing.port import IndexIncompatible
import pytest


def test_rebuild_rotates_generation_and_drops_old_proofs(tmp_path):
    root = tmp_path / "canonical"
    backend = FilesystemBackend(root, tmp_path / "history")
    backend.store(Memory("doc", content="genuine"))
    idx = VerifiedSqliteFts5Index(tmp_path / "derived.db", alias="eidolon_rotation")
    idx.upsert_verified(Memory("doc", content="genuine"), canonical_sha256="b" * 64)
    previous = idx.active_generation()
    assert idx.evidence_for("doc") is not None
    idx.rebuild(root)
    current = idx.active_generation()
    assert current != previous
    assert idx.evidence_for("doc") is None
    with pytest.raises(IndexIncompatible):
        idx.inventory_page(generation=previous)
    assert idx.query("genuine")


def test_legacy_unverified_document_stays_unverified(tmp_path):
    idx = VerifiedSqliteFts5Index(tmp_path / "derived.db", alias="eidolon_legacy")
    idx.upsert(Memory("unverified", content="old source"))
    assert idx.evidence_for("unverified") is None
    page = idx.inventory_page(generation=idx.active_generation())
    assert len(page.records) == 1
    assert page.records[0].evidence is None


def test_bad_digest_never_updates_previous_good_proof(tmp_path):
    idx = VerifiedSqliteFts5Index(tmp_path / "derived.db", alias="eidolon_digest")
    original = idx.upsert_verified(Memory("doc", content="one"), canonical_sha256="a"*64)
    with pytest.raises(ValueError):
        idx.upsert_verified(Memory("doc", content="two"), canonical_sha256="bad")
    assert idx.evidence_for("doc") == original
    assert idx.query("one")
    assert not idx.query("two")
