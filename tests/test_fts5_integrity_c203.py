"""C203 adversarial probes: evidence correctness under metadata corruption.

The current experimental adapter must fail closed when a verified record
diverges from the corresponding document or generation.
"""
import json
import sqlite3
import pytest

from core.backend.models import Memory
from core.indexing.fts5_verified_experimental import VerifiedSqliteFts5Index
from core.indexing.port import IndexIncompatible


def test_corrupt_evidence_revision_must_not_be_accepted(tmp_path):
    index = VerifiedSqliteFts5Index(tmp_path / "proof.db", alias="eidolon_integrity")
    index.upsert_verified(Memory("doc", content="hello", revision=1), canonical_sha256="a"*64)
    with sqlite3.connect(index.path) as db:
        db.execute("UPDATE verified SET revision=99 WHERE information_id='doc'")
    with pytest.raises(IndexIncompatible):
        index.evidence_for("doc")


def test_corrupt_evidence_generation_must_be_rejected(tmp_path):
    index = VerifiedSqliteFts5Index(tmp_path / "proof.db", alias="eidolon_integrity")
    index.upsert_verified(Memory("doc", content="hello", revision=1), canonical_sha256="a"*64)
    with sqlite3.connect(index.path) as db:
        db.execute("UPDATE verified SET generation='stale' WHERE information_id='doc'")
    with pytest.raises(IndexIncompatible):
        index.evidence_for("doc")


def test_evidence_without_document_is_rejected(tmp_path):
    index = VerifiedSqliteFts5Index(tmp_path / "proof.db", alias="eidolon_integrity")
    index.upsert_verified(Memory("doc", content="hello", revision=1), canonical_sha256="a"*64)
    with sqlite3.connect(index.path) as db:
        db.execute("DELETE FROM documents WHERE information_id='doc'")
    with pytest.raises(IndexIncompatible):
        index.evidence_for("doc")
