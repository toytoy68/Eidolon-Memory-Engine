# ==========================================================
# Projet      : Eidolon Memory Engine
# Organisation: Eidolon Core Technologies (ECT)
# Fichier     : tests/claude_memory_eval/test_worker_reference_g214.py
# Description : Recette isolée Claude du worker (G214-3) : lecture échouée, ABSENT prouvé, crash, Qdrant absent
# Standard    : Eidolon Presentation Standard v1
# ==========================================================
"""Contract tests for the future index worker, run against Claude's reference worker and in-memory doubles.
No Qdrant, no Markdown, no VM. GPT's worker should pass the same scenarios (swap ReferenceWorker)."""
import hashlib
import os

import pytest

from core.indexing.change_journal import ChangeJournal
from core.indexing.journal_migration import migrate_v2
from core.indexing.reconcile_plan import Canonical
from tests.claude_memory_eval.reference_worker import Crash, FakeCanon, FakeIndex, ReferenceWorker


def sha(text):
    return hashlib.sha256(text.encode()).hexdigest()


class World:
    def __init__(self, tmp_path):
        self.path = tmp_path / "changes.sqlite3"
        ChangeJournal(self.path)
        migrate_v2(self.path)
        self.journal = ChangeJournal(self.path)
        self.canon, self.index = FakeCanon(), FakeIndex()
        self.allowed = {"alice": None}                     # None = every id; else a set of ids
        self.lock = tmp_path / "worker.lock"
        self.now = None

    def rights(self, profile, ident):
        scope = self.allowed.get(profile, set())
        return scope is None or ident in scope

    def clock(self):
        return self.now if self.now is not None else __import__("time").time()

    def worker(self, profile="alice", **kwargs):
        return ReferenceWorker(self.journal, self.canon, self.index, self.rights, profile=profile,
                               lock_path=str(self.lock), clock=self.clock, **kwargs)

    def write(self, ident, revision, text, *, crash=None):
        """Canonical writer protocol: begin -> rename -> published, with optional crash points."""
        seq = self.journal.begin(ident, revision, "UPSERT", sha(text))
        if crash == "before_rename":
            return seq
        self.canon.docs[ident] = Canonical(revision, sha(text))
        if crash == "before_published":
            return seq
        self.journal.published(seq)
        return seq

    def states(self):
        return {i.sequence: i.state for i in self.journal.pending()}


@pytest.fixture
def world(tmp_path):
    os.chmod(tmp_path, 0o700)
    return World(tmp_path)


def test_nominal_write_is_indexed_once_and_replay_is_a_no_op(world):
    seq = world.write("doc", 1, "v1")
    first = world.worker().run_once()
    assert first.applied == [("INDEX_UPSERT", "doc", seq)]
    assert world.index.points["doc"][0] == 1 and world.states() == {}
    again = world.worker().run_once()
    assert again.applied == [] and world.index.writes == 1


def test_unreadable_canon_means_no_effect_at_all(world):
    seq = world.write("doc", 1, "v1")
    world.index.points["old"] = (3, sha("x"))
    world.canon.unreadable |= {"doc", "old"}
    report = world.worker().run_once()
    assert report.applied == [] and report.proposed_deletions == []
    assert world.states() == {seq: "PUBLISHED"} and world.index.points == {"old": (3, sha("x"))}


def test_proven_absence_only_proposes_a_deletion_never_executes_it(world):
    world.index.points["gone"] = (2, sha("x"))
    report = world.worker().run_once()
    assert report.proposed_deletions == [("gone", None)]
    assert world.index.points == {"gone": (2, sha("x"))}


def test_deletion_is_not_even_proposed_if_the_document_reappears_before_verification(world):
    world.index.points["back"] = (2, sha("x"))

    class Racing(FakeCanon):
        def read(self, ident):
            self.docs["back"] = Canonical(3, sha("y"))              # recreated after the plan
            return super().read(ident)
    racing = Racing()
    world.canon = racing
    report = world.worker().run_once()
    assert report.proposed_deletions == [] and ("back", "absence not confirmed") in report.skipped


def test_crash_between_upsert_and_indexed_replays_without_duplicate(world):
    seq = world.write("doc", 1, "v1")
    with pytest.raises(Crash):
        world.worker(crash_at="after_upsert").run_once()
    assert world.states() == {seq: "PUBLISHED"} and world.index.writes == 1
    world.worker().run_once()
    assert world.states() == {} and world.index.writes == 1


def test_crash_after_rename_before_published_is_recovered_in_two_rounds(world):
    seq = world.write("doc", 1, "v1", crash="before_published")
    assert world.worker().run_once().applied == [("MARK_PUBLISHED", "doc", seq)]
    assert world.worker().run_once().applied == [("INDEX_UPSERT", "doc", seq)]
    assert world.states() == {} and world.index.writes == 1


def test_crash_before_rename_waits_then_asks_for_review_never_closes_alone(world):
    seq = world.write("doc", 1, "v1", crash="before_rename")
    created = world.journal.pending()[0].created
    world.now = created + 5
    assert world.worker().run_once().review == []
    world.now = created + 601
    report = world.worker().run_once()
    assert report.review == [("CLOSE_ABANDONED", "doc", seq)]
    assert world.states() == {seq: "INTENT"} and world.index.points == {}


def test_index_unavailable_marks_nothing_and_recovers(world):
    seq = world.write("doc", 1, "v1")
    world.index.available = False
    assert world.worker().run_once().status == "INDEX_UNAVAILABLE"
    assert world.states() == {seq: "PUBLISHED"}
    world.index.available = True
    world.worker().run_once()
    assert world.states() == {} and world.index.points["doc"][0] == 1


def test_canon_changed_between_plan_and_action_is_not_indexed_stale(world):
    seq = world.write("doc", 1, "v1")

    class Moving(FakeCanon):
        def read(self, ident):
            self.docs[ident] = Canonical(2, sha("v2"))
            return super().read(ident)
    moving = Moving()
    moving.docs = dict(world.canon.docs)
    world.canon = moving
    report = world.worker().run_once()
    assert ("doc", "canon changed since plan") in report.skipped
    assert world.index.points == {} and world.states() == {seq: "PUBLISHED"}


def test_two_fast_revisions_supersede_the_older_and_index_only_the_latest(world):
    first = world.write("doc", 1, "v1")
    second = world.write("doc", 2, "v2")
    world.worker().run_once()
    world.worker().run_once()
    assert world.index.points["doc"] == (2, sha("v2")) and world.states() == {}
    with __import__("sqlite3").connect(world.path) as raw:
        assert raw.execute("SELECT state FROM intents WHERE seq=?", (first,)).fetchone()[0] == "SUPERSEDED"
        assert raw.execute("SELECT state FROM intents WHERE seq=?", (second,)).fetchone()[0] == "INDEXED"


def test_a_profile_without_rights_changes_nothing(world):
    seq = world.write("doc", 1, "v1")
    world.allowed = {"bob": {"other"}}
    report = world.worker(profile="bob").run_once()
    assert ("doc", "forbidden") in report.skipped
    assert world.index.points == {} and world.states() == {seq: "PUBLISHED"}


def test_a_second_worker_is_busy_and_does_nothing(world):
    import fcntl
    world.write("doc", 1, "v1")
    fd = os.open(world.lock, os.O_RDWR | os.O_CREAT, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        assert world.worker().run_once().status == "BUSY"
        assert world.index.points == {}
    finally:
        os.close(fd)


# --- G214 blocking list (docs/G214-INDEX-WORKER-ACCEPTANCE.md, 36c8b8d) -----------------------------------

def test_lost_acknowledgement_is_not_reported_as_success_and_replays_once(world):
    seq = world.write("doc", 1, "v1")
    world.index.lose_next_ack = True
    assert world.worker().run_once().status == "INDEX_UNAVAILABLE"
    assert world.states() == {seq: "PUBLISHED"}                      # not marked indexed on an unknown outcome
    world.worker().run_once()
    assert world.states() == {} and world.index.writes == 1


def test_canon_modified_while_embeddings_are_computed_is_not_marked_indexed(world):
    seq = world.write("doc", 1, "v1")

    def edit():
        world.canon.docs["doc"] = Canonical(2, sha("v2"))
    report = world.worker(hooks={"before_upsert": edit}).run_once()
    assert ("doc", "canon changed while indexing") in report.skipped
    assert world.states() == {seq: "PUBLISHED"}
    world.worker().run_once()
    world.worker().run_once()
    assert world.index.points["doc"] == (2, sha("v2"))


def test_rights_revoked_between_plan_and_action_stop_the_action(world):
    seq = world.write("doc", 1, "v1")

    def revoke():
        world.allowed = {"alice": set()}
    report = world.worker(hooks={"after_plan": revoke}).run_once()
    assert ("doc", "forbidden") in report.skipped
    assert world.index.points == {} and world.states() == {seq: "PUBLISHED"}


def test_embedding_model_or_chunker_change_refuses_any_write(world):
    world.write("doc", 1, "v1")
    world.index.model = ("embed-other/2", "passage-v1")
    assert world.worker().run_once().status == "INDEX_INCOMPATIBLE"
    world.index.model = ("embed-test/1", "passage-v2")
    assert world.worker().run_once().status == "INDEX_INCOMPATIBLE"
    assert world.index.points == {}


def test_truncated_journal_and_clock_behind_intents_change_nothing(world):
    for i in range(1000):
        world.journal.begin(f"doc-{i}", 1, "DELETE")
    assert world.worker().run_once().status == "TRUNCATED"
    assert len(world.journal.pending(limit=1000)) == 1000


def test_a_clock_set_backwards_refuses_the_round(world):
    seq = world.write("doc", 1, "v1")
    world.now = world.journal.pending()[0].created - 3600
    assert world.worker().run_once().status == "REFUSED"
    assert world.states() == {seq: "PUBLISHED"} and world.index.points == {}


def test_two_concurrent_workers_apply_each_effect_once(world, tmp_path):
    import threading
    seqs = [world.write(f"doc-{i}", 1, f"v{i}") for i in range(5)]
    reports, barrier = [], threading.Barrier(2)

    def run():
        barrier.wait()
        reports.append(world.worker().run_once().status)
    threads = [threading.Thread(target=run) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(30)
    world.worker().run_once()
    assert world.states() == {} and world.index.writes == len(seqs)
    assert set(reports) <= {"DONE", "BUSY"}