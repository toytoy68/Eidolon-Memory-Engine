# ==========================================================
# Projet      : Eidolon Memory Engine
# Organisation: Eidolon Core Technologies (ECT)
# Fichier     : tests/claude_memory_eval/test_real_worker_contract_g220.py
# Description : Contrat Claude G220-3 contre le vrai worker (JournalUpsertWorker), Markdown réel, Qdrant en mémoire
# Standard    : Eidolon Presentation Standard v1
# ==========================================================
"""Scenarios of the 19-scenario contract that GPT's real-worker tests do not pin, run against
core.indexing.worker_journal.JournalUpsertWorker. Two of them kill mutants that survive GPT's suite: removing
the final rights or final canonical check before INDEXED. Nothing leaves the process; no deletion exists."""
import pytest

from core.backend.filesystem import FilesystemBackend
from core.backend.models import Memory
from core.indexing.change_journal import ChangeJournal
from core.indexing.qdrant_index import QdrantIndex
from core.indexing.worker_canonical import CanonicalReader
from core.indexing.worker_journal import JournalUpsertWorker

qdrant = pytest.importorskip("qdrant_client")


class World:
    def __init__(self, tmp_path):
        self.root = tmp_path / "persistent"
        self.backend = FilesystemBackend(self.root, tmp_path / "history")
        self.journal = ChangeJournal(tmp_path / "changes.sqlite3")
        self.client = qdrant.QdrantClient(":memory:")
        self.index = QdrantIndex(self.client, "eidolon_claude_contract", embed=lambda _: [1.0, 0.0],
                                 dimensions=2, embedding_id="synthetic-v1", create=True)
        self.decisions = []                                  # scripted authorization answers, else True
        self.calls = 0

    def authorize(self, profile, ident, operation):
        self.calls += 1
        return self.decisions.pop(0) if self.decisions else True

    def write(self, ident, revision, text, *, rename=True, publish=True):
        """Canonical writer protocol: begin -> rename -> published."""
        memory = Memory(ident, content=text, revision=revision)
        digest = None
        if rename:
            if revision == 1:
                self.backend.store(memory)
            else:
                self.backend.update(ident, memory, previous_revision=revision - 1)
            _, digest = CanonicalReader(self.root)(ident)
        seq = self.journal.begin(ident, revision, "UPSERT", digest or "0" * 64)
        if rename and publish:
            self.journal.published(seq)
        return seq

    def worker(self):
        return JournalUpsertWorker(self.journal, canonical_root=self.root, index=self.index,
                                   authorize=self.authorize, profile_id="owner", expected_profile_id="owner",
                                   expected_model_id="synthetic-v1")

    def states(self):
        return {i.sequence: i.state for i in self.journal.pending(limit=999)}


@pytest.fixture
def world(tmp_path):
    w = World(tmp_path)
    yield w
    w.client.close()


def _lose_ack(world):
    original = world.index.upsert_verified

    def once(*args, **kwargs):
        world.index.upsert_verified = original
        original(*args, **kwargs)
        raise ConnectionError("ack lost")
    world.index.upsert_verified = once


def test_two_fast_revisions_index_the_latest_and_send_the_older_to_review(world):
    first = world.write("doc", 1, "v1")
    second = world.write("doc", 2, "v2")
    report = world.worker().run_once()
    assert (first, "SUPERSEDED_REQUIRES_REVIEW") in report.deferred and second in report.indexed
    assert world.index.evidence_for("doc").revision == 2 and world.states() == {first: "PUBLISHED"}


def test_a_write_that_never_reached_the_canon_is_never_published_nor_indexed(world):
    world.write("doc", 1, "v1")
    world.worker().run_once()
    orphan = world.write("doc", 2, "v2", rename=False)               # crash between begin() and rename
    for _ in range(3):
        report = world.worker().run_once()
        assert orphan not in report.published and orphan not in report.indexed
    assert world.states() == {orphan: "INTENT"} and world.index.evidence_for("doc").revision == 1


def test_rights_revoked_on_the_recovery_path_never_mark_indexed(world):
    """Lost ack: the point exists, so no upsert runs and only the worker's final checks guard INDEXED."""
    seq = world.write("doc", 1, "v1")
    _lose_ack(world)
    assert world.worker().run_once().status == "INDEX_UNAVAILABLE"
    world.decisions = [True, False]                                  # initial check passes, final check denies
    report = world.worker().run_once()
    assert seq not in report.indexed and world.states() == {seq: "PUBLISHED"}


def test_canon_changed_on_the_recovery_path_never_marks_indexed(world):
    """Lost ack, then the document changes between the worker's first read and its final check."""
    seq = world.write("doc", 1, "v1")
    _lose_ack(world)
    world.worker().run_once()
    backend = world.backend

    def authorize(profile, ident, operation):
        world.calls += 1
        if world.calls == 2:                                         # after the first read, before the final one
            backend.update("doc", Memory("doc", content="v2", revision=2), previous_revision=1)
        return True
    world.calls = 0
    world.authorize = authorize
    report = world.worker().run_once()
    assert seq not in report.indexed and world.states() == {seq: "PUBLISHED"}


def test_no_code_path_can_remove_a_point(world):
    world.write("doc", 1, "v1")
    world.worker().run_once()
    seq = world.journal.begin("doc", 2, "DELETE")
    report = world.worker().run_once()
    assert (seq, "DELETE_REQUIRES_REVIEW") in report.deferred
    assert world.index.evidence_for("doc").revision == 1
    assert not any(hasattr(world.worker(), name) for name in ("delete", "apply_delete", "remove"))
