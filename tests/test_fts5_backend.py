"""Isolated FTS5 backend contract and failure recovery checks."""
import sqlite3

from core.backend.fts5_backend import FTS5Backend
from core.backend.models import Memory


def make_backend(tmp_path):
    return FTS5Backend(
        persistent_root=tmp_path / "canonical",
        history_root=tmp_path / "history",
    )


def test_store_update_and_search(tmp_path):
    backend = make_backend(tmp_path)
    assert backend.search("anything") == []
    backend.store(Memory(information_id="item-1", content="alpha old fact"))
    assert backend.search("alpha")[0].memory.information_id == "item-1"

    backend.update(
        "item-1", Memory(information_id="item-1", content="beta corrected fact"), 1
    )
    assert backend.search("alpha") == []
    assert backend.search("beta")[0].memory.revision == 2


def test_delete_requires_approval(tmp_path):
    backend = make_backend(tmp_path)
    backend.store(Memory(information_id="item-1", content="secret test memory"))
    backend.delete_request("item-1", "tester", "test", 1, "op-1")
    assert backend.search("secret")
    backend.cancel_delete("item-1", "op-1")
    assert backend.search("secret")
    backend.delete_request("item-1", "tester", "test", 1, "op-2")
    backend.approve_delete("item-1", "op-2")
    assert backend.search("secret") == []


def test_restart_repairs_stale_index(tmp_path):
    backend = make_backend(tmp_path)
    backend.store(Memory(information_id="item-1", content="remember me"))
    with sqlite3.connect(backend.db_path) as connection:
        connection.execute("DROP TABLE memories_fts")
    recovered = make_backend(tmp_path)
    assert recovered.search("remember")[0].memory.information_id == "item-1"
    assert recovered.rebuild_index()["indexed"] == 1


def test_canonical_file_remains_authoritative(tmp_path):
    backend = make_backend(tmp_path)
    backend.store(Memory(information_id="item-1", content="temporary entry"))
    (tmp_path / "canonical" / "item-1.md").unlink()
    assert backend.search("temporary") == []
    assert make_backend(tmp_path).rebuild_index()["indexed"] == 0


def test_special_query_cannot_inject_sql(tmp_path):
    backend = make_backend(tmp_path)
    backend.store(Memory(information_id="item-1", content="alpha"))
    assert backend.search('alpha"; DROP TABLE memories_fts;--') is not None
    assert len(backend.search("alpha")) == 1
