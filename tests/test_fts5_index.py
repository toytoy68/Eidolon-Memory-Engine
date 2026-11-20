# ==========================================================
# Projet      : Eidolon Memory Engine
# Organisation: Eidolon Core Technologies (ECT)
# Fichier     : tests/test_fts5_index.py
# Description : SQLite FTS5 IndexPort: unchanged contract and parity with the reference index.
# Standard    : Eidolon Presentation Standard v1
# ==========================================================

import random
import stat

import pytest

from core.backend.filesystem import FilesystemBackend
from core.backend.models import Memory
from core.indexing.fts5_index import SqliteFts5Index
from core.indexing.memory_index import InMemoryIndex
from tests.contracts.index_port_contract import IndexPortContract


class TestSqliteFts5Index(IndexPortContract):
    @pytest.fixture
    def index(self, tmp_path):
        (tmp_path / "index").mkdir()
        return SqliteFts5Index(tmp_path / "index" / "fts5.sqlite3")


WORDS = ("réseau fibre moteur robotique jardin pommes hydraulique eau stockage disques "
         "Eidolon mémoire rappel souvenir livre chapitre serveur cave refroidissement").split()


def _corpus(seed, n):
    rng = random.Random(seed)
    for i in range(n):
        yield Memory(f"m{i}", content=" ".join(rng.choice(WORDS) for _ in range(rng.randint(3, 12))),
                     metadata={"topic": rng.choice(WORDS), "owner": rng.choice(("alice", "bob"))})


def test_ranking_parity_with_reference_index(tmp_path):
    reference, fts = InMemoryIndex(), SqliteFts5Index(tmp_path / "fts5.sqlite3", candidate_floor=1000)
    for memory in _corpus(7, 300):
        reference.upsert(memory); fts.upsert(memory)
    rng = random.Random(11)
    for _ in range(60):
        query = " ".join(rng.choice(WORDS) for _ in range(rng.randint(1, 3)))
        expected = [(h.information_id, round(h.score, 9)) for h in reference.query(query, limit=10)]
        got = [(h.information_id, round(h.score, 9)) for h in fts.query(query, limit=10)]
        assert got == expected, query


def test_json_key_names_are_not_terms(tmp_path):
    fts = SqliteFts5Index(tmp_path / "fts5.sqlite3")
    fts.upsert(Memory("a", content="pommes", metadata={"owner": "alice"}))
    assert fts.query("owner") == [] and [h.information_id for h in fts.query("alice")] == ["a"]


def test_persists_across_reopen_and_is_private(tmp_path):
    path = tmp_path / "fts5.sqlite3"
    SqliteFts5Index(path).upsert(Memory("a", content="souvenir durable"))
    assert [h.information_id for h in SqliteFts5Index(path).query("souvenir")] == ["a"]
    assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_rebuild_swaps_atomically_and_records_the_manifest(tmp_path):
    persistent = tmp_path / "memory" / "persistent"
    backend = FilesystemBackend(persistent, tmp_path / "memory" / "history")
    for memory in _corpus(3, 40):
        backend.store(memory)
    fts = SqliteFts5Index(tmp_path / "fts5.sqlite3")
    fts.rebuild(persistent)
    assert fts.status().documents == 40
    assert not list(tmp_path.glob("fts5.sqlite3.rebuild*"))


def test_query_with_quote_and_operators_is_literal(tmp_path):
    fts = SqliteFts5Index(tmp_path / "fts5.sqlite3")
    fts.upsert(Memory("a", content="alpha"))
    assert [h.information_id for h in fts.query('alpha" OR NEAR(x) NOT *')] == ["a"]
