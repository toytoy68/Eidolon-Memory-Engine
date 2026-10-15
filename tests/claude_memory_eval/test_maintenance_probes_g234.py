# ==========================================================
# Projet      : Eidolon Memory Engine
# Organisation: Eidolon Core Technologies (ECT)
# Fichier     : tests/claude_memory_eval/test_maintenance_probes_g234.py
# Description : Contre-revue Claude G229-G234 : cycle de maintenance, arriérés, orphelins, horloge
# Standard    : Eidolon Presentation Standard v1
# ==========================================================
"""Scenarios not covered by tests/test_index_maintenance.py, on the real IndexMaintenance with real Markdown and
in-memory Qdrant. Positive tests pin behaviour; characterisation tests pin a limit GPT must decide on."""
from datetime import datetime, timedelta, timezone

import pytest

from core.backend.filesystem import FilesystemBackend
from core.backend.models import Memory
from core.indexing.change_journal import ChangeJournal
from core.indexing.worker_canonical import CanonicalReader

qdrant = pytest.importorskip("qdrant_client")
from core.indexing.qdrant_index import QdrantIndex          # noqa: E402


class World:
    def __init__(self, base):
        self.base, self.root = base, base / "persistent"
        self.backend = FilesystemBackend(self.root, base / "history")
        self.journal = ChangeJournal(base / "changes.sqlite3")
        self.client = qdrant.QdrantClient(":memory:")
        self.index = QdrantIndex(self.client, "eidolon_claude_maint", embed=lambda _: [1., 0.], dimensions=2,
                                 embedding_id="synthetic-v1", create=True)
        self.writes = 0
        original = self.index.upsert_verified

        def counting(*args, **kwargs):
            self.writes += 1
            return original(*args, **kwargs)
        self.index.upsert_verified = counting
        self.options = dict(canonical_root=self.root, index=self.index, authorize=lambda *a: True,
                            profile_id="owner", expected_profile_id="owner", expected_model_id="synthetic-v1")
        # 03:00 UTC = inside the Paris 04:00-08:00 window (CEST and CET), in the future of every intent.
        self.at = datetime.now(timezone.utc).replace(hour=3, minute=0, second=0, microsecond=0) + timedelta(days=1)

    def write(self, ident, *, intent=True):
        self.backend.store(Memory(ident, content="synthetic " + ident))
        if intent:
            _, digest = CanonicalReader(self.root)(ident)
            self.journal.published(self.journal.begin(ident, 1, "UPSERT", digest))

    def cycle(self, **kwargs):
        from core.indexing.maintenance import IndexMaintenance
        opts = dict(canonical_checkpoint=self.base / "canonical.sqlite3",
                    orphan_checkpoint=self.base / "orphans.sqlite3", page_size=100, pending_limit=100,
                    **self.options)
        opts.update(kwargs)
        return IndexMaintenance(self.base / "cycle.sqlite3", self.journal, **opts)

    def tick(self, at=None):
        at = at or self.at
        return self.cycle().tick(at=at, last_activity=at - timedelta(hours=1), boot_at=at - timedelta(hours=2),
                                 load_ok=True)

    def finish(self, limit=400):
        for _ in range(limit):
            report = self.tick()
            if report.state in ("CYCLE_COMPLETE", "REVIEW_REQUIRED"):
                return report
            assert report.state in ("ACTIVE", "RESTART_REQUIRED"), report
            self.at += timedelta(seconds=1)
        pytest.fail("cycle did not finish")

    def next_cycle(self):
        self.at += timedelta(minutes=10)                       # past cycle_seconds (300 s)
        return self.finish()


@pytest.fixture
def world(tmp_path):
    w = World(tmp_path)
    yield w
    w.client.close()


def test_a_backlog_of_1200_healthy_upserts_is_fully_indexed_once(world):
    """G234 priority 'pagination with backlog > 1000', for valid work (GPT's test covers 1005 reviews)."""
    for i in range(1200):
        world.write(f"doc-{i:04d}")
    assert world.finish().state == "CYCLE_COMPLETE"
    assert world.journal.pending(limit=1) == () and world.writes == 1200
    assert world.index.status().documents == 1200


def test_after_a_rebuild_maintenance_recovers_provenance_without_deleting(world):
    """G235 regression for corrected Q1: rebuild retains provenance, no maintenance re-embedding.
    Nothing is deleted; the old generation is kept."""
    for i in range(5):
        world.write(f"doc-{i}")
    assert world.finish().state == "CYCLE_COMPLETE" and world.writes == 5
    world.index.rebuild(world.root)
    states = [world.next_cycle().state for _ in range(3)]
    assert states[-1] == "CYCLE_COMPLETE"
    assert world.writes == 5                                    # rebuild proofs avoid another worker encoding
    assert all(world.index.evidence_for(f"doc-{i}") is not None for i in range(5))
    assert len(world.client.get_collections().collections) == 2


def test_a_forward_clock_jump_requires_explicit_audited_recovery(world):
    """G236: original Claude stall probe retained, followed by explicit recovery.
    The original 0036 patch remains archived in Core; no automatic reset."""
    world.write("doc")
    assert world.tick(at=world.at + timedelta(days=365)).state == "ACTIVE"
    for days in (0, 1, 30):
        assert world.tick(at=world.at + timedelta(days=days)).state == "CLOCK_REVERSED"
    assert world.journal.pending(limit=1) != ()
    receipt = world.cycle().recover_clock(at=world.at,
        expected_last_at=(world.at + timedelta(days=365)).timestamp(), expected_cycle=1,
        actor="claude-probe", reason="G236 explicit clock correction", request_id="mt1")
    assert receipt["cycle"] == 2 and world.finish().state == "CYCLE_COMPLETE"


def test_orphan_limit_is_reported_and_controller_accepts_a_sufficient_budget(world):
    """G236: preserve Claude's insufficient-budget probe and verify a configured
    controller with separate checkpoints completes at the exact sufficient bound."""
    from core.indexing.maintenance import IndexMaintenance
    from core.indexing.orphan_scan import OrphanScan
    for i in range(3):
        world.write(f"doc-{i}")
    world.finish()
    scan = OrphanScan(world.base / "orphan-small.sqlite3", world.journal, max_points=2, **world.options)
    states = [scan.run_page(limit=1).state for _ in range(8)]
    assert "EXHAUSTED" not in states and states[-3:] == ["LIMIT_REACHED"] * 3     # stuck at the same place
    again = [scan.run_page(limit=1, restart=True).state] + [scan.run_page(limit=1).state for _ in range(7)]
    assert "EXHAUSTED" not in again and again[-1] == "LIMIT_REACHED"            # a new pass hits the same wall
    cycle = IndexMaintenance(world.base / "bounded-cycle.sqlite3", world.journal,
        canonical_checkpoint=world.base / "bounded-canonical.sqlite3",
        orphan_checkpoint=world.base / "bounded-orphan.sqlite3", max_points=3, **world.options)
    for _ in range(30):
        result = cycle.tick(at=world.at, last_activity=world.at-timedelta(hours=1),
                            boot_at=world.at-timedelta(hours=2), load_ok=True)
        if result.state == "CYCLE_COMPLETE":
            break
    assert result.state == "CYCLE_COMPLETE"


def test_process_death_after_the_point_write_and_before_indexed_resumes_without_re_embedding(world):
    """G234 priority 'resume after effect before checkpoint', variant not in GPT's suite: the Qdrant point is
    written, then the process dies BEFORE the journal reaches INDEXED and before the controller checkpoint. On
    resume the existing point is verified and adopted: INDEXED without a second embedding, nothing deleted."""
    import os
    import subprocess
    import sys
    from pathlib import Path
    world.client.close()
    world.client = qdrant.QdrantClient(path=str(world.base / "qdrant"))
    world.index = QdrantIndex(world.client, "eidolon_claude_maint", embed=lambda _: [1., 0.], dimensions=2,
                              embedding_id="synthetic-v1", create=True)
    world.options["index"] = world.index
    world.write("doc")
    seq = world.journal.pending()[0].sequence
    assert world.tick().state == "ACTIVE"                        # fence persisted, no effect yet
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
original = ChangeJournal.advance_verified
def die_before_indexed(self, expected, after):
    if after == "INDEXED":
        os._exit(74)                                  # the point is already written and verified
    return original(self, expected, after)
ChangeJournal.advance_verified = die_before_indexed
client = QdrantClient(path=str(base / "qdrant"))
index = QdrantIndex(client, "eidolon_claude_maint", embed=lambda _: [1., 0.], dimensions=2,
                    embedding_id="synthetic-v1")
cycle = IndexMaintenance(base / "cycle.sqlite3", ChangeJournal(base / "changes.sqlite3"),
    canonical_checkpoint=base / "canonical.sqlite3", orphan_checkpoint=base / "orphans.sqlite3",
    canonical_root=base / "persistent", index=index, authorize=lambda *a: True, profile_id="owner",
    expected_profile_id="owner", expected_model_id="synthetic-v1", page_size=100, pending_limit=100)
cycle.tick(at=at, last_activity=at-timedelta(hours=1), boot_at=at-timedelta(hours=2), load_ok=True)
'''
    env = dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[2]))
    result = subprocess.run([sys.executable, "-c", code, str(world.base), world.at.isoformat()],
                            env=env, capture_output=True, text=True, timeout=60)
    assert result.returncode == 74, result.stderr
    world.client = qdrant.QdrantClient(path=str(world.base / "qdrant"))

    def no_embedding(_):
        pytest.fail("a verified point was embedded a second time")
    world.index = QdrantIndex(world.client, "eidolon_claude_maint", embed=no_embedding, dimensions=2,
                              embedding_id="synthetic-v1")
    world.options["index"] = world.index
    assert world.journal.intent(seq).state == "PUBLISHED"
    assert world.index.evidence_for("doc") is not None          # the effect survived the crash
    world.at += timedelta(seconds=1)
    assert world.finish().state == "CYCLE_COMPLETE"
    assert world.journal.intent(seq).state == "INDEXED" and world.index.status().documents == 1
