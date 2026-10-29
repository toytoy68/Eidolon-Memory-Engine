"""Worker evidence and generation smoke tests for a disposable isolated index."""
from hashlib import sha256
import pytest

from core.backend.models import Memory
from core.indexing.fts5_verified_experimental import VerifiedSqliteFts5Index
from core.indexing.port import IndexIncompatible


def make(tmp_path):
    return VerifiedSqliteFts5Index(tmp_path / "proof.db", alias="eidolon_test")


def test_verified_write_and_readback(tmp_path):
    index = make(tmp_path)
    memory = Memory("a", content="alpha evidence")
    proof = index.upsert_verified(memory, canonical_sha256="a"*64)
    assert index.evidence_for("a") == proof
    assert proof.generation == index.active_generation()
    assert index.query("alpha")[0].information_id == "a"


def test_ordinary_write_clears_claim(tmp_path):
    index = make(tmp_path)
    index.upsert_verified(Memory("a", content="old"), canonical_sha256="a"*64)
    index.upsert(Memory("a", content="new"))
    assert index.evidence_for("a") is None


def test_generation_persists_on_reopen(tmp_path):
    original = make(tmp_path)
    generation = original.active_generation()
    same = make(tmp_path)
    assert same.active_generation() == generation
    with pytest.raises(IndexIncompatible):
        VerifiedSqliteFts5Index(tmp_path / "proof.db", alias="eidolon_other")


def test_paged_inventory_and_generation_fence(tmp_path):
    index = make(tmp_path)
    for i in range(5):
        index.upsert_verified(Memory(f"id{i}", content="item"), canonical_sha256=f"{i}"*64)
    generation = index.active_generation()
    collected = []
    offset = None
    while True:
        page = index.inventory_page(generation=generation, offset=offset, limit=2)
        collected += [r.information_id for r in page.records]
        offset = page.next_offset
        if offset is None:
            break
    assert collected == [f"id{i}" for i in range(5)]
    with pytest.raises(IndexIncompatible):
        index.inventory_page(generation="old", limit=2)


def test_bad_digest_rejected(tmp_path):
    index = make(tmp_path)
    with pytest.raises(ValueError):
        index.upsert_verified(Memory("a", content="a"), canonical_sha256="wrong")
    assert index.evidence_for("a") is None
