"""C204 cross-instance generation races (disposable data only)."""
import concurrent.futures
from core.backend.filesystem import FilesystemBackend
from core.backend.models import Memory
from core.indexing.fts5_verified_experimental import VerifiedSqliteFts5Index
from core.indexing.port import IndexIncompatible


def test_concurrent_rebuild_and_verified_updates_keep_consistent_proofs(tmp_path):
    root = tmp_path / "canon"
    base = FilesystemBackend(root, tmp_path / "history")
    for i in range(15):
        base.store(Memory(f"doc{i}", content=f"stable document {i}"))
    path = tmp_path / "index.sqlite3"
    first = VerifiedSqliteFts5Index(path, alias="eidolon_race")
    second = VerifiedSqliteFts5Index(path, alias="eidolon_race")
    first.rebuild(root)

    def rebuild():
        for _ in range(12):
            first.rebuild(root)

    def writer():
        for i in range(60):
            second.upsert_verified(
                Memory("live", content=f"live event {i}", revision=i + 1),
                canonical_sha256=f"{i % 10}" * 64,
            )

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        jobs = [pool.submit(rebuild), pool.submit(writer)]
        for job in jobs:
            job.result()

    generation = first.active_generation()
    proof = first.evidence_for("live")
    if proof is not None:
        assert proof.generation == generation
        page = first.inventory_page(generation=generation, limit=100)
        assert any(record.information_id == "live" and record.evidence == proof for record in page.records)
    else:
        assert not any(hit.information_id == "live" for hit in first.query("live"))
    assert first.status().documents >= 15


def test_reentrant_lock_nested_generation_access(tmp_path):
    index = VerifiedSqliteFts5Index(tmp_path / "index.sqlite3", alias="eidolon_lock")
    evidence = index.upsert_verified(Memory("a", content="nested"), canonical_sha256="a"*64)
    assert index.evidence_for("a") == evidence
    assert index.inventory_page(generation=evidence.generation).records[0].evidence == evidence
