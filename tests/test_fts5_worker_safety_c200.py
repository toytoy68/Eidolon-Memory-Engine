"""C200: safety gates before an optional FTS5 journal-worker integration.

A plain IndexPort can be rebuilt from stopped canonical snapshots, but it
must not be substituted for WorkerIndexPort (verified write provenance).
"""
import pytest

from core.indexing.fts5_index import SqliteFts5Index
from core.indexing.worker_journal import JournalUpsertWorker


def test_fts5_is_not_a_verified_worker_port(tmp_path):
    adapter = SqliteFts5Index(tmp_path / "fts5.db")
    required = (
        "active_generation",
        "evidence_for",
        "upsert_verified",
        "inventory_page",
        "embedding_id",
        "alias",
    )
    unsupported = [member for member in required if not hasattr(adapter, member)]
    assert unsupported, "Never wire FTS5 into the verified worker without explicit evidence contract"
    assert set(unsupported) >= {
        "active_generation", "evidence_for", "upsert_verified",
        "inventory_page", "embedding_id", "alias"
    }


def test_worker_rejects_unverified_fts5_adapter(tmp_path):
    adapter = SqliteFts5Index(tmp_path / "fts5.db")
    with pytest.raises(ValueError, match="invalid journal worker configuration"):
        JournalUpsertWorker(
            object(),
            canonical_root=tmp_path / "canonical",
            index=adapter,
            authorize=lambda *args: True,
            profile_id="owner",
            expected_profile_id="owner",
            expected_model_id="placeholder",
        )


def test_rebuild_failure_keeps_last_good_index(tmp_path, monkeypatch):
    from core.backend.filesystem import FilesystemBackend
    from core.backend.models import Memory
    root = tmp_path / "canonical"
    backend = FilesystemBackend(persistent_root=root, history_root=tmp_path / "history")
    backend.store(Memory("first", content="alpha unique"))
    adapter = SqliteFts5Index(tmp_path / "fts5.db")
    adapter.rebuild(root)
    previous = adapter.query("alpha")
    assert [hit.information_id for hit in previous] == ["first"]

    import core.indexing.fts5_index as module
    original_put = module.SqliteFts5Index._put
    def interrupted(db, memory):
        raise RuntimeError("simulated interruption before database replacement")
    monkeypatch.setattr(module.SqliteFts5Index, "_put", staticmethod(interrupted))
    with pytest.raises(RuntimeError, match="simulated interruption"):
        adapter.rebuild(root)
    monkeypatch.setattr(module.SqliteFts5Index, "_put", original_put)
    assert adapter.query("alpha") == previous
