"""C202 disposable integration: real ChangeJournal + verified FTS5 adapter.

No production runtime registration. Explicitly tests a private canonical scope.
"""
from core.backend.filesystem import FilesystemBackend
from core.backend.models import Memory
from core.indexing.change_journal import ChangeJournal
from core.indexing.worker_canonical import CanonicalReader
from core.indexing.worker_journal import JournalUpsertWorker
from core.indexing.fts5_verified_experimental import VerifiedSqliteFts5Index


def test_real_worker_journal_verified_replay(tmp_path):
    root = tmp_path / "canonical"
    backend = FilesystemBackend(root, tmp_path / "history")
    journal = ChangeJournal(tmp_path / "journal.sqlite3")
    index = VerifiedSqliteFts5Index(tmp_path / "index.sqlite3", alias="eidolon_worker_test")
    memory = Memory("doc", content="indexed alpha")
    backend.store(memory)
    _, digest = CanonicalReader(root)("doc")
    sequence = journal.begin("doc", 1, "UPSERT", digest)
    journal.published(sequence)

    def worker(allowed=True):
        return JournalUpsertWorker(
            journal, canonical_root=root, index=index,
            authorize=lambda *_: allowed, profile_id="user1",
            expected_profile_id="user1", expected_model_id=index.embedding_id,
        )

    first = worker().run_once()
    assert first.indexed == (sequence,)
    assert index.evidence_for("doc").canonical_sha256 == digest
    assert worker().run_once().indexed == ()
    assert index.query("alpha")[0].information_id == "doc"


def test_denied_worker_does_not_write(tmp_path):
    root = tmp_path / "canonical"
    backend = FilesystemBackend(root, tmp_path / "history")
    journal = ChangeJournal(tmp_path / "journal.sqlite3")
    index = VerifiedSqliteFts5Index(tmp_path / "index.sqlite3", alias="eidolon_worker_test")
    backend.store(Memory("doc", content="private document"))
    _, digest = CanonicalReader(root)("doc")
    seq = journal.begin("doc", 1, "UPSERT", digest)
    journal.published(seq)
    result = JournalUpsertWorker(
        journal, canonical_root=root, index=index, authorize=lambda *_: False,
        profile_id="user1", expected_profile_id="user1",
        expected_model_id=index.embedding_id,
    ).run_once()
    assert result.deferred == ((seq, "FORBIDDEN"),)
    assert index.evidence_for("doc") is None
