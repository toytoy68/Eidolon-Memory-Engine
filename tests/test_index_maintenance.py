# ==========================================================
# Projet      : Eidolon Memory Engine
# Organisation: Eidolon Core Technologies (ECT)
# Fichier     : tests/test_index_maintenance.py
# Description : Fair journal pages and durable index maintenance on local stores.
# Standard    : Eidolon Presentation Standard v1
# ==========================================================
from datetime import datetime, timedelta, timezone
import pytest
from core.backend.filesystem import FilesystemBackend
from core.backend.models import Memory
from core.indexing.change_journal import ChangeJournal
from core.indexing.worker_canonical import CanonicalReader
from core.indexing.worker_journal import JournalUpsertWorker

qdrant = pytest.importorskip("qdrant_client")
from core.indexing.qdrant_index import QdrantIndex


@pytest.fixture
def world(tmp_path):
    class World:
        def __init__(self):
            self.base = tmp_path
            self.root = tmp_path / "persistent"
            self.backend = FilesystemBackend(self.root, tmp_path / "history")
            self.journal = ChangeJournal(tmp_path / "changes.sqlite3")
            self.client = qdrant.QdrantClient(":memory:")
            self.index = QdrantIndex(self.client, "eidolon_maintenance", embed=lambda _: [1., 0.],
                                     dimensions=2, embedding_id="synthetic-v1", create=True)
            self.allowed = True
            self.options = dict(canonical_root=self.root, index=self.index,
                authorize=lambda *args: self.allowed, profile_id="owner",
                expected_profile_id="owner", expected_model_id="synthetic-v1")
            # Future relative to intent creation, inside the Paris 04:00–08:00 window.
            self.at = datetime.now(timezone.utc).replace(hour=3, minute=0, second=0, microsecond=0) + timedelta(days=1)

        def write(self, ident="doc", intent=True, published=True):
            self.backend.store(Memory(ident, content="synthetic"))
            if not intent:
                return None
            _, digest = CanonicalReader(self.root)(ident)
            seq = self.journal.begin(ident, 1, "UPSERT", digest)
            if published:
                self.journal.published(seq)
            return seq

        def worker(self):
            return JournalUpsertWorker(self.journal, **self.options)

        def cycle(self, **kwargs):
            from core.indexing.maintenance import IndexMaintenance
            opts = dict(canonical_checkpoint=self.base / "canonical.sqlite3",
                        orphan_checkpoint=self.base / "orphans.sqlite3",
                        page_size=2, pending_limit=2, **self.options)
            opts.update(kwargs)
            return IndexMaintenance(self.base / "cycle.sqlite3", self.journal, **opts)

        def tick(self, **kwargs):
            opts = dict(at=self.at, last_activity=self.at-timedelta(hours=1),
                        boot_at=self.at-timedelta(hours=2), load_ok=True)
            opts.update(kwargs)
            return self.cycle().tick(**opts)

        def finish(self, count=150):
            for _ in range(count):
                report = self.tick()
                if report.state in ("CYCLE_COMPLETE", "REVIEW_REQUIRED"):
                    return report
                assert report.state in ("ACTIVE", "RESTART_REQUIRED"), report
            pytest.fail("cycle did not finish")

    w = World()
    yield w
    w.client.close()


def test_review_at_front_does_not_starve_later_upserts(world):
    blocked = world.journal.begin("removed", 1, "DELETE")
    good = [world.write("doc"+str(i)) for i in range(4)]
    page = world.worker().run_page(limit=2)
    assert page.result.indexed == (good[0],)
    while not page.exhausted:
        page = world.worker().run_page(after=page.after, through=page.through, limit=2)
    assert [i.sequence for i in world.journal.pending()] == [blocked]
    assert world.index.status().documents == 4


def test_fixed_pass_does_not_chase_new_arrivals(world):
    first = world.write("a")
    world.write("b")
    page = world.worker().run_page(limit=1)
    later = world.write("c")
    assert page.after == first and page.through < later
    page = world.worker().run_page(after=page.after, through=page.through, limit=1)
    assert page.exhausted and [i.sequence for i in world.journal.pending()] == [later]


def test_durable_cycle_recovers_lost_events_and_finishes_without_delete(world):
    for ident in ("a", "b", "c", "d", "e"):
        world.write(ident, intent=False)
    for _ in range(100):
        report = world.tick()  # rebuild the controller from disk every tick
        if report.state == "CYCLE_COMPLETE":
            break
    else:
        pytest.fail("cycle did not finish")
    assert world.journal.pending() == ()
    assert world.index.status().documents == 5
    assert world.tick().state == "WAITING"


def test_more_than_one_thousand_reviews_do_not_starve_valid_tail(world):
    for i in range(1005):
        world.journal.begin("removed"+str(i), 1, "DELETE")
    good = world.write("tail")
    assert world.worker().run_once().status == "TRUNCATED"  # legacy contract unchanged
    after, through, seen = 0, None, []
    for _ in range(20):
        page = world.worker().run_page(after=after, through=through, limit=100)
        seen.extend(seq for seq, _ in page.result.deferred)
        after, through = page.after, page.through
        if page.exhausted:
            break
    assert len(seen) == len(set(seen)) == 1005
    assert world.journal.intent(good).state == "INDEXED"
    assert world.index.status().documents == 1

    controller_tail = world.write("controller_tail")
    for _ in range(100):
        report = world.cycle(page_size=100, pending_limit=100).tick(
            at=world.at, last_activity=world.at-timedelta(hours=1),
            boot_at=world.at-timedelta(hours=2), load_ok=True)
        if report.state == "REVIEW_REQUIRED":
            break
    else:
        pytest.fail("large backlog never reached durable review")
    assert world.journal.intent(controller_tail).state == "INDEXED"
    after, total = 0, 0
    for _ in range(20):
        page = world.cycle(page_size=100, pending_limit=100).reviews(after=after)
        total += len(page["items"])
        if page["next_after"] is None:
            break
        after = page["next_after"]
    assert total == 1005


def test_terminal_holes_and_compacted_history_preserve_fence(world):
    seq = world.journal.begin("gone", 1, "DELETE")
    world.journal.close_terminal(seq, "ABANDONED", "isolated fixture")
    import sqlite3
    with sqlite3.connect(world.journal.path) as db:
        db.execute("DELETE FROM intents WHERE seq=?", (seq,))
    assert world.journal.high_watermark() == seq
    page = world.worker().run_page(through=seq)
    assert page.exhausted and page.after == seq
    assert world.write() > seq


def test_intent_publication_is_consumed_on_next_finite_pass(world):
    seq = world.write(published=False)
    first = world.worker().run_page()
    assert first.exhausted and first.result.published == (seq,)
    assert world.index.status().documents == 0
    second = world.worker().run_page()
    assert second.exhausted and second.result.indexed == (seq,)


def test_partial_index_outage_keeps_failing_row_at_cursor(world, monkeypatch):
    a, b = world.write("a"), world.write("b")
    original = world.index.evidence_for
    def offline(ident):
        if ident == "b":
            raise ConnectionError("offline")
        return original(ident)
    monkeypatch.setattr(world.index, "evidence_for", offline)
    page = world.worker().run_page()
    assert (page.status, page.after, page.through, page.exhausted) == ("INDEX_UNAVAILABLE", a, b, False)
    assert page.result.indexed == (a,)
    monkeypatch.setattr(world.index, "evidence_for", original)
    page = world.worker().run_page(after=page.after, through=page.through)
    assert page.exhausted and page.result.indexed == (b,)


def test_future_timestamp_becomes_review_without_blocking_next_row(world):
    import sqlite3
    bad = world.write("future")
    good = world.write("current")
    with sqlite3.connect(world.journal.path) as db:
        db.execute("UPDATE intents SET created=? WHERE seq=?", (world.at.timestamp()+1, bad))
    page = world.worker().run_page(now=world.at.timestamp())
    assert page.result.deferred == ((bad, "INVALID_TIMESTAMP"),)
    assert page.result.indexed == (good,) and page.exhausted


def test_malformed_canonical_row_does_not_starve_healthy_tail(world):
    bad = world.write("broken")
    good = world.write("healthy")
    (world.root / "broken.md").write_text("not an Information document")
    page = world.worker().run_page()
    assert page.result.deferred == ((bad, "UNVERIFIED"),)
    assert page.result.indexed == (good,)
    assert world.finish().state == "REVIEW_REQUIRED"
    assert world.journal.intent(bad).state == "PUBLISHED"
    assert world.index.status().documents == 1


@pytest.mark.parametrize("options", [dict(after=-1), dict(after=True), dict(after=1),
    dict(after=2, through=1), dict(through=True), dict(limit=1000), dict(now=float("nan"))])
def test_invalid_worker_page_options_refused(world, options):
    world.write()
    with pytest.raises(ValueError):
        world.worker().run_page(**options)
    assert world.index.status().documents == 0


def test_review_saturation_ends_cycle_and_resumes_after_resolution(world):
    blocked = [world.journal.begin("removed"+str(i), 1, "DELETE") for i in range(3)]
    world.write(intent=False)
    result = world.finish()
    assert result.state == "REVIEW_REQUIRED" and result.detail["blocked"]
    review = world.cycle().reviews(limit=2)
    assert [i["sequence"] for i in review["items"]] == blocked[:2]
    assert review["next_after"] == blocked[1]
    assert world.cycle().reviews(after=review["next_after"])["items"][0]["sequence"] == blocked[2]
    assert world.index.status().documents == 0
    for seq in blocked:
        world.journal.close_terminal(seq, "ABANDONED", "isolated review resolved")
    assert world.cycle().reviews()["items"] == []
    world.at += timedelta(seconds=300)
    assert world.finish().state == "CYCLE_COMPLETE"
    assert world.index.status().documents == 1


def test_orphan_cycle_requires_review_and_never_deletes(world, monkeypatch):
    world.index.upsert_verified(Memory("orphan", content="old"), canonical_sha256="a"*64)
    def forbidden(*args, **kwargs):
        pytest.fail("maintenance attempted deletion")
    monkeypatch.setattr(world.client, "delete", forbidden)
    world.write("new", intent=False)
    result = world.finish()
    assert result.state == "REVIEW_REQUIRED" and result.detail["orphan_review"] == 1
    assert world.index.status().documents == 2
    assert world.journal.pending() == ()


def test_revocation_does_not_close_or_lose_pending_work(world):
    seq = world.write()
    world.allowed = False
    assert world.finish().state == "REVIEW_REQUIRED"
    assert world.journal.intent(seq).state == "PUBLISHED"
    assert world.cycle().reviews()["items"][0]["reason"] == "FORBIDDEN"
    world.allowed = True
    world.at += timedelta(seconds=300)
    assert world.finish().state == "CYCLE_COMPLETE"
    assert world.journal.intent(seq).state == "INDEXED"
    assert world.cycle().reviews()["items"] == []


@pytest.mark.parametrize("condition", ["window", "activity", "boot", "load", "unknown_load"])
def test_host_conditions_defer_without_any_index_call(world, monkeypatch, condition):
    world.write()
    cycle = world.cycle()
    args = dict(at=world.at, last_activity=world.at-timedelta(hours=1),
                boot_at=world.at-timedelta(hours=2), load_ok=True)
    if condition == "window":
        args["at"] += timedelta(hours=8)
    elif condition == "activity":
        args["last_activity"] = world.at-timedelta(minutes=29)
    elif condition == "boot":
        args["boot_at"] = world.at-timedelta(minutes=29)
    else:
        args["load_ok"] = False if condition == "load" else 1
    def unexpected():
        pytest.fail("index accessed despite deferred maintenance")
    monkeypatch.setattr(world.index, "active_generation", unexpected)
    report = cycle.tick(**args)
    assert report.state == "DEFERRED" and report.stage == "FIRST"


def test_index_failure_backoff_survives_controller_reconstruction(world, monkeypatch):
    world.write()
    original = world.index.active_generation
    def offline():
        raise ConnectionError("offline")
    monkeypatch.setattr(world.index, "active_generation", offline)
    result = world.tick()
    assert result.state == "INDEX_UNAVAILABLE"
    assert world.cycle().status().detail["last_result"]["state"] == "INDEX_UNAVAILABLE"
    assert world.tick().state == "WAITING"
    monkeypatch.setattr(world.index, "active_generation", original)
    world.at += timedelta(seconds=30)
    assert world.finish().state == "CYCLE_COMPLETE"


def test_activity_between_ticks_preserves_progress(world):
    world.write()
    first = world.tick()
    assert first.detail.get("pass_started") == 1
    assert world.tick(last_activity=world.at).state == "DEFERRED"
    assert world.finish().state == "CYCLE_COMPLETE"


def test_backwards_clock_refuses_progress_and_future_activity_refuses(world):
    world.write()
    world.tick()
    world.at -= timedelta(seconds=1)
    assert world.tick().state == "CLOCK_REVERSED"
    with pytest.raises(ValueError, match="last_activity"):
        world.tick(last_activity=world.at+timedelta(seconds=1))


def test_periodic_next_cycle_finds_new_document(world):
    world.write("first", intent=False)
    initial = world.finish()
    world.write("later", intent=False)
    assert world.tick().state == "WAITING"
    world.at += timedelta(seconds=300)
    final = world.finish()
    assert final.cycle == initial.cycle+1
    assert world.index.status().documents == 2


def test_generation_switch_restarts_both_scans(world):
    world.write(intent=False)
    world.tick()
    world.index.rebuild(world.root)
    result = world.tick()
    assert result.state == "RESTART_REQUIRED"
    assert world.finish().state == "CYCLE_COMPLETE"


def test_checkpoint_rejects_changed_policy_and_replaced_journal(world):
    world.tick()
    with pytest.raises(ValueError, match="context"):
        world.cycle(page_size=3)
    from pathlib import Path
    Path(world.journal.path).rename(Path(world.journal.path).with_suffix(".old"))
    world.journal = ChangeJournal(world.journal.path)
    with pytest.raises(ValueError, match="context"):
        world.cycle()


def test_readonly_status_survives_reconstruction_without_index_contact(world, monkeypatch):
    world.finish()
    def unexpected():
        pytest.fail("status touched the live index")
    monkeypatch.setattr(world.index, "active_generation", unexpected)
    status = world.cycle().status()
    assert status.state == "CYCLE_COMPLETE"
    assert status.detail["last_result"]["state"] == "CYCLE_COMPLETE"


def test_mismatching_model_does_not_publish_intents(world):
    seq = world.write(published=False)
    cycle = world.cycle()
    world.index.embedding_id = "other"
    result = cycle.tick(at=world.at, last_activity=world.at-timedelta(hours=1),
                        boot_at=world.at-timedelta(hours=2), load_ok=True)
    assert result.state == "INDEX_INCOMPATIBLE"
    assert world.journal.intent(seq).state == "INTENT"


def test_generation_switch_just_before_final_status_cannot_complete_old_cycle(world):
    world.write(intent=False)
    for _ in range(60):
        report = world.tick()
        if report.stage == "FINISH" and report.detail.get("state") == "EXHAUSTED":
            break
    else:
        pytest.fail("missing final stage")
    world.index.rebuild(world.root)
    assert world.tick().state == "RESTART_REQUIRED"
    assert world.finish().state == "CYCLE_COMPLETE"


def test_checkpoint_paths_cannot_alias_each_other(world):
    with pytest.raises(ValueError, match="separate"):
        world.cycle(canonical_checkpoint=world.base / "cycle.sqlite3")
    import os
    os.link(world.journal.path, world.base / "cycle.sqlite3")
    with pytest.raises(ValueError, match="alias"):
        world.cycle()


def test_corrupt_completed_checkpoint_is_not_a_valid_completion(world):
    import json
    import sqlite3
    world.tick()
    with sqlite3.connect(world.base / "cycle.sqlite3") as db:
        data = json.loads(db.execute("SELECT state FROM maintenance").fetchone()[0])
        data.update(stage="FINISH", outcome="CYCLE_COMPLETE")
        db.execute("UPDATE maintenance SET state=?", (json.dumps(data),))
    with pytest.raises(ValueError, match="invalid maintenance"):
        world.cycle()


def test_new_arrival_during_pass_waits_for_later_fence_and_is_eventually_indexed(world, monkeypatch):
    world.write("first")
    original = world.index.upsert_verified
    added = []
    def arrive(*args, **kwargs):
        if not added:
            added.append(world.write("later"))
        return original(*args, **kwargs)
    monkeypatch.setattr(world.index, "upsert_verified", arrive)
    assert world.finish().state == "CYCLE_COMPLETE"
    assert world.index.status().documents == 2 and world.journal.pending() == ()


def test_concurrent_tick_defers_while_another_writer_holds_lock(world):
    import threading
    from core.persistence import exclusive_write
    cycle = world.cycle()
    reports = []
    with exclusive_write(world.root):
        thread = threading.Thread(target=lambda: reports.append(cycle.tick(
            at=world.at, last_activity=world.at-timedelta(hours=1),
            boot_at=world.at-timedelta(hours=2), load_ok=True)))
        thread.start()
        thread.join(5)
        assert not thread.is_alive()
    assert reports[0].state == "BUSY"


def test_busy_first_worker_page_does_not_invent_an_empty_fence(world):
    import threading
    from core.persistence import exclusive_write
    seq = world.write()
    reports = []
    with exclusive_write(world.root):
        thread = threading.Thread(target=lambda: reports.append(world.worker().run_page()))
        thread.start()
        thread.join(5)
        assert not thread.is_alive()
    assert reports[0].status == "BUSY" and reports[0].through is None
    page = world.worker().run_page(after=reports[0].after, through=reports[0].through)
    assert page.result.indexed == (seq,)


def test_checkpoint_failure_after_canonical_page_replays_idempotently(world, monkeypatch):
    world.write(intent=False)
    for _ in range(10):
        if world.tick().stage == "CANONICAL":
            break
    cycle = world.cycle()
    def fail_save(*args):
        raise RuntimeError("lost controller commit")
    monkeypatch.setattr(cycle, "_save", fail_save)
    with pytest.raises(RuntimeError, match="lost controller"):
        cycle.tick(at=world.at, last_activity=world.at-timedelta(hours=1),
                   boot_at=world.at-timedelta(hours=2), load_ok=True)
    assert len(world.journal.pending()) == 1
    assert world.finish().state == "CYCLE_COMPLETE"
    assert world.journal.high_watermark() == 1


def test_real_process_exit_after_worker_effect_replays_controller_checkpoint(world):
    from pathlib import Path
    import os
    import subprocess
    import sys
    world.client.close()
    world.client = qdrant.QdrantClient(path=str(world.base / "qdrant"))
    world.index = QdrantIndex(world.client, "eidolon_maintenance", embed=lambda _: [1., 0.],
                              dimensions=2, embedding_id="synthetic-v1", create=True)
    world.options["index"] = world.index
    seq = world.write()
    assert world.tick().detail["pass_started"] == seq
    world.client.close()
    code = '''
import os, sys
from pathlib import Path
from datetime import datetime, timedelta
from qdrant_client import QdrantClient
from core.indexing.qdrant_index import QdrantIndex
from core.indexing.change_journal import ChangeJournal
from core.indexing.maintenance import IndexMaintenance
base, at = Path(sys.argv[1]), datetime.fromisoformat(sys.argv[2])
client = QdrantClient(path=str(base / "qdrant"))
index = QdrantIndex(client, "eidolon_maintenance", embed=lambda _: [1., 0.], dimensions=2, embedding_id="synthetic-v1")
cycle = IndexMaintenance(base / "cycle.sqlite3", ChangeJournal(base / "changes.sqlite3"),
    canonical_checkpoint=base / "canonical.sqlite3", orphan_checkpoint=base / "orphans.sqlite3",
    canonical_root=base / "persistent", index=index, authorize=lambda *args: True,
    profile_id="owner", expected_profile_id="owner", expected_model_id="synthetic-v1", page_size=2, pending_limit=2)
def crash(db, state):
    assert state["stage"] == "SECOND"
    os._exit(73)
cycle._save = crash
cycle.tick(at=at, last_activity=at-timedelta(hours=1), boot_at=at-timedelta(hours=2), load_ok=True)
'''
    env = dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[1]))
    result = subprocess.run([sys.executable, "-c", code, str(world.base), world.at.isoformat()],
                            env=env, capture_output=True, text=True, timeout=30)
    assert result.returncode == 73, result.stderr
    world.client = qdrant.QdrantClient(path=str(world.base / "qdrant"))
    def no_embedding(_):
        pytest.fail("indexed effect was embedded twice")
    world.index = QdrantIndex(world.client, "eidolon_maintenance", embed=no_embedding,
                              dimensions=2, embedding_id="synthetic-v1")
    world.options["index"] = world.index
    assert world.journal.intent(seq).state == "INDEXED"
    assert world.finish().state == "CYCLE_COMPLETE"
    assert world.index.status().documents == 1
