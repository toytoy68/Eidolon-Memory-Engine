# ==========================================================
# Projet      : Eidolon Memory Engine
# Organisation: Eidolon Core Technologies (ECT)
# Fichier     : tests/test_reconcile_scan.py
# Description : Restartable canonical inventory with real SQLite and Qdrant.
# Standard    : Eidolon Presentation Standard v1
# ==========================================================
import pytest
from core.backend.filesystem import FilesystemBackend
from core.backend.models import Memory
from core.indexing.change_journal import ChangeJournal
from core.indexing.qdrant_index import QdrantIndex
from core.indexing.worker_journal import JournalUpsertWorker

qdrant = pytest.importorskip("qdrant_client")


@pytest.fixture
def world(tmp_path):
    class World:
        def __init__(self):
            self.base = tmp_path
            self.root = tmp_path / "persistent"
            self.backend = FilesystemBackend(self.root, tmp_path / "history")
            self.journal = ChangeJournal(tmp_path / "changes.sqlite3")
            self.checkpoint = tmp_path / "scan.sqlite3"
            self.client = qdrant.QdrantClient(":memory:")
            self.index = QdrantIndex(self.client, "eidolon_scan_test",
                                     embed=lambda _: [1., 0.], dimensions=2,
                                     embedding_id="synthetic-v1", create=True)
            self.allowed = True

        def write(self, ident="doc", revision=1, text="source without event"):
            memory = Memory(ident, revision=revision, content=text)
            if revision == 1:
                self.backend.store(memory)
            else:
                self.backend.update(ident, memory, previous_revision=revision - 1)

        def scanner(self, **kwargs):
            from core.indexing.reconcile_scan import ReconciliationScan
            options = dict(canonical_root=self.root, index=self.index,
                authorize=lambda *args: self.allowed, profile_id="owner",
                expected_profile_id="owner", expected_model_id="synthetic-v1")
            options.update(kwargs)
            return ReconciliationScan(self.checkpoint, self.journal, **options)

        def worker(self):
            return JournalUpsertWorker(
                self.journal, canonical_root=self.root, index=self.index,
                authorize=lambda *args: self.allowed, profile_id="owner",
                expected_profile_id="owner", expected_model_id="synthetic-v1")

    w = World()
    yield w
    w.client.close()


def test_lost_events_recovered_in_pages_and_resume_uses_disk_cursor(world):
    for ident in ("a", "b", "c"):
        world.write(ident)
    first = world.scanner().run_page(limit=1)
    assert first.state == "RUNNING" and first.cursor == 1 and first.total == 3
    assert len(world.journal.pending()) == 1
    second = world.scanner().run_page(limit=1)
    assert second.cursor == 2 and len(world.journal.pending()) == 2
    assert world.scanner().run_page(limit=1).state == "VERIFYING"
    assert world.scanner().run_page(limit=1).state == "COMPLETE"
    assert len(world.journal.pending()) == 3
    assert world.index.status().documents == 0  # scan has no index write authority
    world.worker().run_once()
    world.worker().run_once()
    assert world.journal.pending() == () and world.index.status().documents == 3


def test_document_modified_behind_cursor_forces_another_pass(world):
    world.write("a")
    world.write("b")
    assert world.scanner().run_page(limit=1).cursor == 1
    world.write("a", revision=2)
    assert world.scanner().run_page(limit=1).state == "VERIFYING"
    assert world.scanner().run_page(limit=1).state == "RESTART_REQUIRED"
    world.scanner().run_page(limit=2)
    assert world.scanner().run_page().state == "COMPLETE"
    assert [(i.information_id, i.revision) for i in world.journal.pending()] == [("a", 1), ("b", 1), ("a", 2)]


def test_journal_recovery_enqueue_is_idempotent_and_conflicts_are_not_hidden(world):
    seq = world.journal.ensure_upsert_intent("doc", 1, "a" * 64)
    assert world.journal.ensure_upsert_intent("doc", 1, "a" * 64) == seq
    assert world.journal.ensure_upsert_intent("doc", 1, "b" * 64) is None
    assert len(world.journal.pending()) == 1


def test_new_document_before_cursor_is_found_on_restarted_pass(world):
    world.write("b")
    assert world.scanner().run_page().state == "VERIFYING"
    world.write("a")
    assert world.scanner().run_page().state == "RESTART_REQUIRED"
    world.scanner().run_page()
    assert world.scanner().run_page().state == "COMPLETE"
    assert {i.information_id for i in world.journal.pending()} == {"a", "b"}


def test_queue_capacity_pauses_without_skipping_and_resumes_after_drain(world):
    for ident in ("a", "b", "c"):
        world.write(ident)
    paused = world.scanner(pending_limit=1).run_page(limit=3)
    assert (paused.state, paused.cursor, len(paused.queued)) == ("JOURNAL_FULL", 1, 1)
    assert len(world.journal.pending()) == 1
    world.worker().run_once()
    world.worker().run_once()
    paused = world.scanner(pending_limit=1).run_page(limit=3)
    assert (paused.state, paused.cursor) == ("JOURNAL_FULL", 2)
    world.worker().run_once()
    world.worker().run_once()
    assert world.scanner(pending_limit=1).run_page().state == "VERIFYING"
    assert world.scanner(pending_limit=1).run_page().state == "COMPLETE"
    assert [i.information_id for i in world.journal.pending()] == ["c"]


def test_index_unavailable_after_one_document_preserves_page_progress(world, monkeypatch):
    world.write("a")
    world.write("b")
    original = world.index.evidence_for
    def unavailable(ident):
        if ident == "b":
            raise ConnectionError("offline")
        return original(ident)
    monkeypatch.setattr(world.index, "evidence_for", unavailable)
    paused = world.scanner().run_page()
    assert (paused.state, paused.cursor) == ("INDEX_UNAVAILABLE", 1)
    assert len(paused.queued) == 1
    monkeypatch.setattr(world.index, "evidence_for", original)
    assert world.scanner().run_page().cursor == 2
    assert len(world.journal.pending()) == 2


@pytest.mark.parametrize("allowed", [False, 1, "yes", None])
def test_denied_documents_are_durable_review_items(world, allowed):
    world.write()
    world.allowed = allowed
    page = world.scanner().run_page()
    assert page.review_count == 1
    assert world.scanner().run_page().state == "REVIEW_REQUIRED"
    assert world.scanner().issues() == (("doc", "FORBIDDEN"),)
    assert world.journal.pending() == ()


def test_revocation_during_point_read_prevents_enqueue(world, monkeypatch):
    world.write()
    original = world.index.evidence_for
    def revoke(ident):
        world.allowed = False
        return original(ident)
    monkeypatch.setattr(world.index, "evidence_for", revoke)
    assert world.scanner().run_page().review_count == 1
    assert world.journal.pending() == ()


def test_point_digest_conflict_is_reviewed_not_overwritten(world):
    from core.indexing.worker_canonical import CanonicalReader
    world.write()
    memory, _ = CanonicalReader(world.root)("doc")
    world.index.upsert_verified(memory, canonical_sha256="0" * 64)
    assert world.scanner().run_page().review_count == 1
    assert world.scanner().run_page().state == "REVIEW_REQUIRED"
    assert world.scanner().issues() == (("doc", "INDEX_CONFLICT"),)
    assert world.index.evidence_for("doc").canonical_sha256 == "0" * 64
    assert world.journal.pending() == ()


def test_matching_point_needs_no_new_intent_and_explicit_restart_checks_again(world):
    from core.indexing.worker_canonical import CanonicalReader
    world.write()
    memory, digest = CanonicalReader(world.root)("doc")
    world.index.upsert_verified(memory, canonical_sha256=digest)
    assert world.scanner().run_page().queued == ()
    assert world.scanner().run_page().state == "COMPLETE"
    world.write("new")
    assert world.scanner().run_page().state == "COMPLETE"  # historical pass
    assert world.scanner().run_page(restart=True).state == "VERIFYING"
    assert [i.information_id for i in world.journal.pending()] == ["new"]


def test_old_point_and_legacy_point_both_receive_recovery_intents(world):
    from core.indexing.worker_canonical import CanonicalReader
    world.write("old")
    memory, digest = CanonicalReader(world.root)("old")
    world.index.upsert_verified(memory, canonical_sha256=digest)
    world.write("old", revision=2)
    world.write("legacy")
    memory, _ = CanonicalReader(world.root)("legacy")
    world.index.upsert(memory)
    assert len(world.scanner().run_page().queued) == 2
    assert {(i.information_id, i.revision) for i in world.journal.pending()} == {("old", 2), ("legacy", 1)}


@pytest.mark.parametrize("operation,revision,digest", [("DELETE", 1, None), ("UPSERT", 2, "a" * 64),
                                                      ("UPSERT", 1, "b" * 64)])
def test_pending_conflict_is_not_hidden_by_another_intent(world, operation, revision, digest):
    world.write()
    world.journal.begin("doc", revision, operation, digest)
    assert world.scanner().run_page().review_count == 1
    assert world.scanner().issues() == (("doc", "JOURNAL_CONFLICT"),)
    assert len(world.journal.pending()) == 1


def test_deletion_between_pages_restarts_without_deleting_index(world):
    from core.indexing.worker_canonical import CanonicalReader
    world.write("a")
    world.write("b")
    memory, digest = CanonicalReader(world.root)("b")
    world.index.upsert_verified(memory, canonical_sha256=digest)
    world.scanner().run_page(limit=1)
    (world.root / "b.md").unlink()
    assert world.scanner().run_page().state == "RESTART_REQUIRED"
    world.scanner().run_page()
    assert world.scanner().run_page().state == "COMPLETE"
    assert world.index.evidence_for("b") is not None


@pytest.mark.parametrize("budget", [dict(max_entries=1), dict(max_file_bytes=1), dict(max_total_bytes=1)])
def test_exceeded_budget_never_certifies_a_truncated_inventory(world, budget):
    world.write()
    with pytest.raises(ValueError, match="limit"):
        world.scanner(**budget).run_page()
    assert world.journal.pending() == ()
    assert world.scanner().run_page().state == "VERIFYING"  # checkpoint can recover with adequate budget


def test_symlink_source_refused_before_any_intent(world):
    world.write()
    (world.root / "alias.md").symlink_to(world.root / "doc.md")
    with pytest.raises(ValueError, match="unsafe"):
        world.scanner().run_page()
    assert world.journal.pending() == ()


def test_checkpoint_cannot_be_reused_for_another_profile_or_journal(world):
    world.write()
    world.scanner().run_page()
    with pytest.raises(ValueError, match="context"):
        world.scanner(profile_id="other").run_page()
    world.journal = ChangeJournal(world.base / "other.sqlite3")
    with pytest.raises(ValueError, match="context"):
        world.scanner().run_page()
    assert world.journal.pending() == ()


def test_generation_change_restarts_the_pass(world):
    world.write()
    world.scanner().run_page()
    world.index.rebuild(world.root)
    assert world.scanner().run_page().state == "RESTART_REQUIRED"
    world.scanner().run_page()
    assert world.scanner().run_page().state == "COMPLETE"
    assert len(world.journal.pending()) == 1


def test_model_mismatch_refuses_before_queueing(world):
    world.write()
    world.index.embedding_id = "other"
    assert world.scanner().run_page().state == "INDEX_INCOMPATIBLE"
    assert world.journal.pending() == ()


def test_two_scanners_do_not_duplicate_intents(world):
    import threading
    world.write("a")
    world.write("b")
    scanners = [world.scanner(), world.scanner()]
    barrier = threading.Barrier(2)
    results, errors = [], []
    def run(scanner):
        try:
            barrier.wait(timeout=5)
            results.append(scanner.run_page(limit=1))
        except BaseException as exc:
            errors.append(exc)
    threads = [threading.Thread(target=run, args=(s,)) for s in scanners]
    for t in threads:
        t.start()
    for t in threads:
        t.join(10)
        assert not t.is_alive()
    assert not errors
    world.scanner().run_page()
    assert len(world.journal.pending()) == 2
    assert all(r.state in ("RUNNING", "VERIFYING", "BUSY") for r in results)


def test_process_death_after_journal_commit_does_not_duplicate_on_resume(world):
    import subprocess
    import sys
    import textwrap
    world.write("a")
    world.write("b")
    world.client.close()
    def reopen(create=False):
        world.client = qdrant.QdrantClient(path=str(world.base / "qdrant"))
        world.index = QdrantIndex(world.client, "eidolon_scan_test", embed=lambda _: [1., 0.],
                                 dimensions=2, embedding_id="synthetic-v1", create=create)
    reopen(create=True)
    assert world.scanner().run_page(limit=1).cursor == 1
    world.client.close()
    child = textwrap.dedent('''
        import os, sys
        from pathlib import Path
        from qdrant_client import QdrantClient
        from core.indexing.change_journal import ChangeJournal
        from core.indexing.qdrant_index import QdrantIndex
        from core.indexing.reconcile_scan import ReconciliationScan
        base=Path(sys.argv[1])
        journal=ChangeJournal(base / "changes.sqlite3")
        original=journal.ensure_upsert_intent
        def crash(*args, **kwargs):
            original(*args, **kwargs)
            os._exit(73)
        journal.ensure_upsert_intent=crash
        client=QdrantClient(path=str(base / "qdrant"))
        index=QdrantIndex(client, "eidolon_scan_test", embed=lambda _: [1.,0.],
                          dimensions=2, embedding_id="synthetic-v1")
        ReconciliationScan(base / "scan.sqlite3", journal, canonical_root=base / "persistent", index=index,
                           authorize=lambda *args: True, profile_id="owner", expected_profile_id="owner",
                           expected_model_id="synthetic-v1").run_page(limit=1)
    ''')
    result = subprocess.run([sys.executable, "-c", child, str(world.base)],
                            capture_output=True, text=True, timeout=30)
    assert result.returncode == 73, result.stderr
    assert [i.information_id for i in world.journal.pending()] == ["a", "b"]
    reopen()
    assert world.scanner().run_page(limit=1).cursor == 2
    assert len(world.journal.pending()) == 2
    assert world.scanner().run_page().state == "COMPLETE"


def test_same_revision_edit_behind_cursor_is_not_certified(world):
    world.write("a")
    world.write("b")
    world.scanner().run_page(limit=1)
    path = world.root / "a.md"
    path.write_text(path.read_text().replace("source without event", "changed without revision"))
    world.scanner().run_page()
    assert world.scanner().run_page().state == "RESTART_REQUIRED"
    world.scanner().run_page()
    assert world.scanner().run_page().state == "REVIEW_REQUIRED"
    assert world.scanner().issues() == (("a", "JOURNAL_CONFLICT"),)


def test_canonical_change_during_index_read_is_rechecked_before_enqueue(world, monkeypatch):
    world.write()
    original = world.index.evidence_for
    def change(ident):
        world.write(revision=2)
        return original(ident)
    monkeypatch.setattr(world.index, "evidence_for", change)
    assert world.scanner().run_page().state == "RESTART_REQUIRED"
    assert world.journal.pending() == ()


def test_alias_switch_during_point_read_does_not_enqueue(world, monkeypatch):
    world.write()
    original = world.index.evidence_for
    def switch(ident):
        point = original(ident)
        world.index.rebuild(world.root)
        return point
    monkeypatch.setattr(world.index, "evidence_for", switch)
    assert world.scanner().run_page().state == "RESTART_REQUIRED"
    assert world.journal.pending() == ()


@pytest.mark.parametrize("change", ["cursor=2", "phase='COMPLETE'"])
def test_invalid_checkpoint_cursor_cannot_skip_unprocessed_documents(world, change):
    import sqlite3
    world.write("a")
    world.write("b")
    world.scanner().run_page(limit=1)
    with sqlite3.connect(world.checkpoint) as db:
        db.execute("UPDATE scan SET " + change)
    with pytest.raises(ValueError, match="checkpoint"):
        world.scanner().run_page()
    assert len(world.journal.pending()) == 1


def test_matching_pending_intent_can_be_reused_at_capacity(world):
    seq = world.journal.ensure_upsert_intent("doc", 1, "a" * 64, pending_limit=1)
    assert world.journal.ensure_upsert_intent("doc", 1, "a" * 64, pending_limit=1) == seq
    from core.indexing.change_journal import JournalCapacityExceeded
    with pytest.raises(JournalCapacityExceeded):
        world.journal.ensure_upsert_intent("other", 1, "b" * 64, pending_limit=1)
    assert len(world.journal.pending()) == 1
