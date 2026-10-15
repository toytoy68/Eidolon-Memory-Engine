# ==========================================================
# Projet      : Eidolon Memory Engine
# Organisation: Eidolon Core Technologies (ECT)
# Fichier     : tests/claude_memory_eval/test_g236_g237_reviews.py
# Description : Contre-revue Claude G236 (MT1, MT3) et G237 (R1, lecture canonique bornée)
# Standard    : Eidolon Presentation Standard v1
# ==========================================================
"""Independent probes on the real IndexMaintenance / JournalUpsertWorker. GPT's files are not modified."""
import multiprocessing
import os
import sqlite3
from datetime import timedelta

import pytest

from core.backend.models import Memory
from core.indexing.worker_canonical import CanonicalReader
from tests.claude_memory_eval.test_maintenance_probes_g234 import World

qdrant = pytest.importorskip("qdrant_client")


@pytest.fixture
def world(tmp_path):
    w = World(tmp_path)
    yield w
    w.client.close()


def _jump_and_correct(world):
    """One tick a year ahead, then the corrected clock: returns (fault report, last_at, cycle)."""
    world.write("doc")
    ahead = world.at + timedelta(days=365)
    assert world.tick(at=ahead).state == "ACTIVE"
    report = world.tick()
    assert report.state == "CLOCK_REVERSED"
    status = world.cycle().status()
    return report, status.detail["last_at"], status.cycle


def _journal_and_index(world):
    return ([(i.sequence, i.state) for i in world.journal.pending(limit=999)], world.writes,
            world.index.status().documents)


# --- MT1: explicit, audited clock recovery -----------------------------------------------------------------

def test_mt1_recovery_restarts_the_cycle_without_touching_journal_or_index(world):
    report, last_at, cycle = _jump_and_correct(world)
    assert report.detail.get("review_required") is True
    before = _journal_and_index(world)
    receipt = world.cycle().recover_clock(at=world.at, expected_last_at=last_at, expected_cycle=cycle,
                                          actor="toytoy", reason="horloge corrigée", request_id="clk-1")
    assert receipt["cycle"] == cycle + 1 and _journal_and_index(world) == before
    world.at += timedelta(seconds=1)
    assert world.finish().state == "CYCLE_COMPLETE" and world.journal.pending(limit=1) == ()
    audit = world.cycle().clock_recoveries()["items"]
    assert [r["request_id"] for r in audit] == ["clk-1"] and audit[0]["actor"] == "toytoy"


def test_mt1_stale_or_unfounded_requests_are_refused(world):
    with pytest.raises(ValueError):                                      # no fault yet
        world.write("doc")
        world.tick()
        status = world.cycle().status()
        world.cycle().recover_clock(at=world.at - timedelta(hours=1), expected_last_at=status.detail["last_at"],
                                    expected_cycle=status.cycle, actor="a", reason="r", request_id="x-0")


def test_mt1_stale_state_and_reused_ids_are_refused_and_retries_are_idempotent(world):
    _, last_at, cycle = _jump_and_correct(world)
    c = world.cycle()
    for wrong in (dict(expected_last_at=last_at - 1, expected_cycle=cycle),
                  dict(expected_last_at=last_at, expected_cycle=cycle + 1)):
        with pytest.raises(ValueError):
            c.recover_clock(at=world.at, actor="a", reason="r", request_id="stale", **wrong)
    first = c.recover_clock(at=world.at, expected_last_at=last_at, expected_cycle=cycle, actor="a",
                            reason="r", request_id="clk-2")
    again = world.cycle().recover_clock(at=world.at, expected_last_at=last_at, expected_cycle=cycle, actor="a",
                                        reason="r", request_id="clk-2")
    assert again == first and world.cycle().status().cycle == cycle + 1      # applied once
    with pytest.raises(ValueError):
        world.cycle().recover_clock(at=world.at, expected_last_at=last_at, expected_cycle=cycle, actor="a",
                                    reason="other", request_id="clk-2")


def test_mt1_a_crash_inside_the_recovery_transaction_leaves_the_fault_and_allows_a_retry(world):
    _, last_at, cycle = _jump_and_correct(world)
    path = world.base / "cycle.sqlite3"
    before = sqlite3.connect(path).execute("SELECT state FROM maintenance").fetchone()
    cycle_obj = world.cycle()
    ctx = multiprocessing.get_context("fork")

    def child():
        real = sqlite3.connect

        class Dying:
            def __init__(self, conn):
                self.conn = conn

            def execute(self, sql, *a):
                if "DELETE FROM clock_fault" in sql:
                    os._exit(19)                              # receipt inserted, state saved, not committed
                return self.conn.execute(sql, *a)

            def __getattr__(self, name):
                return getattr(self.conn, name)

            def __enter__(self):
                self.conn.__enter__()
                return self

            def __exit__(self, *exc):
                return self.conn.__exit__(*exc)
        sqlite3.connect = lambda *a, **k: Dying(real(*a, **k))
        cycle_obj.recover_clock(at=world.at, expected_last_at=last_at, expected_cycle=cycle, actor="a",
                                reason="r", request_id="clk-crash")
        os._exit(0)
    process = ctx.Process(target=child)
    process.start()
    process.join(30)
    assert process.exitcode == 19
    raw = sqlite3.connect(path)
    assert raw.execute("SELECT state FROM maintenance").fetchone() == before
    assert raw.execute("SELECT count(*) FROM clock_recoveries").fetchone()[0] == 0
    assert raw.execute("SELECT count(*) FROM clock_fault").fetchone()[0] == 1
    raw.close()
    receipt = world.cycle().recover_clock(at=world.at, expected_last_at=last_at, expected_cycle=cycle, actor="a",
                                          reason="r", request_id="clk-crash")
    assert receipt["cycle"] == cycle + 1


# --- MT3: orphan budget bound to the checkpoint context -----------------------------------------------------

def test_mt3_limit_is_configurable_bound_to_context_and_never_certifies_an_incomplete_inventory(world):
    for i in range(4):
        world.write(f"doc-{i}")
    small = lambda: world.cycle(max_points=2)                              # noqa: E731
    report = None
    for _ in range(200):
        report = small().tick(at=world.at, last_activity=world.at - timedelta(hours=1),
                              boot_at=world.at - timedelta(hours=2), load_ok=True)
        if report.state in ("CYCLE_COMPLETE", "REVIEW_REQUIRED"):
            break
        world.at += timedelta(seconds=1)
    assert report.state == "REVIEW_REQUIRED"                                # 4 points > 2: never complete
    for other in (dict(), dict(max_points=3)):                              # implicit change refused
        with pytest.raises(ValueError):
            world.cycle(**other)


# --- R1: bounded canonical reads in the journal worker ------------------------------------------------------

def _worker(world, **kw):
    from core.indexing.worker_journal import JournalUpsertWorker
    return JournalUpsertWorker(world.journal, **world.options, **kw)


def test_r1_an_oversized_document_is_deferred_never_embedded_and_does_not_block_the_next(world):
    world.backend.store(Memory("big", content="x" * 5000))
    _, digest = CanonicalReader(world.root)("big")
    big = world.journal.begin("big", 1, "UPSERT", digest)
    world.journal.published(big)
    world.write("small")
    embedded = []
    world.index.embed = lambda text: embedded.append(text) or [1.0, 0.0]
    report = _worker(world, max_file_bytes=1024).run_once()
    assert (big, "CANONICAL_TOO_LARGE") in report.deferred
    assert len(report.indexed) == 1 and world.index.evidence_for("big") is None
    assert all("x" * 100 not in t for t in embedded)


def test_r1_a_file_growing_past_the_budget_is_refused_by_the_reader(world, tmp_path):
    world.backend.store(Memory("doc", content="court"))
    path = world.root / "doc.md"
    size = path.stat().st_size
    reader = CanonicalReader(world.root, max_bytes=size + 10)
    reader("doc")                                                            # within budget
    with open(path, "ab") as handle:
        handle.write(b"y" * 50)                                              # grows past the budget
    with pytest.raises(ValueError):
        reader("doc")


# --- Q1 (G236-1): a rebuild never rewrites the previous generation --------------------------------------------

def test_q1_rebuild_leaves_every_point_of_the_previous_generation_untouched(world):
    for i in range(3):
        world.write(f"doc-{i}")
    world.finish()
    old = world.index.active_generation()

    def snapshot(name):
        points, _ = world.client.scroll(name, limit=100, with_payload=True, with_vectors=True)
        return sorted((str(p.id), sorted(p.payload.items()), list(p.vector)) for p in points)
    before = snapshot(old)
    world.backend.update("doc-0", Memory("doc-0", content="nouveau", revision=2), previous_revision=1)
    world.index.rebuild(world.root)
    assert world.index.active_generation() != old and snapshot(old) == before
