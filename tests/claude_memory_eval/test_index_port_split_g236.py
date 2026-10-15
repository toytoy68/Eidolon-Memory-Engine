# ==========================================================
# Projet      : Eidolon Memory Engine
# Organisation: Eidolon Core Technologies (ECT)
# Fichier     : tests/claude_memory_eval/test_index_port_split_g236.py
# Description : Expérience isolée Claude Q2 (G236-7) : vue « worker » de l'index, sans suppression ni reconstruction
# Standard    : Eidolon Presentation Standard v1
# ==========================================================
"""Isolated experiment for the Q2 proposal (Core docs/proposals/2026-10-15-index-port-split.md). IndexPort and
QdrantIndex are unchanged: a narrowing view proves that the whole worker/scan/maintenance path needs only six
members, and that deletion, rebuild and the provenance-less upsert are then unreachable."""
from datetime import timedelta

import pytest

from tests.claude_memory_eval.test_maintenance_probes_g234 import World

qdrant = pytest.importorskip("qdrant_client")

WORKER_MEMBERS = ("embedding_id", "alias", "active_generation", "evidence_for", "upsert_verified", "inventory_page")
ADMIN_MEMBERS = ("rebuild", "delete", "upsert", "revision_for")


class WorkerIndexView:
    """Exposes only what the journal worker, both scans and the maintenance cycle use."""
    __slots__ = ("_index",)

    def __init__(self, index):
        object.__setattr__(self, "_index", index)

    def __getattr__(self, name):
        if name not in WORKER_MEMBERS:
            raise AttributeError(f"{name} is not part of the worker index port")
        return getattr(object.__getattribute__(self, "_index"), name)

    def __setattr__(self, name, value):
        raise AttributeError("the worker index port is read-only")


@pytest.fixture
def world(tmp_path):
    w = World(tmp_path)
    w.options["index"] = WorkerIndexView(w.index)
    yield w
    w.client.close()


def test_the_full_maintenance_cycle_runs_through_the_narrow_worker_view(world):
    for i in range(5):
        world.write(f"doc-{i}")
    assert world.finish().state == "CYCLE_COMPLETE"
    assert world.index.status().documents == 5 and world.writes == 5
    (world.root / "doc-0.md").unlink()                                 # out-of-band removal of the source
    world.at += timedelta(minutes=10)
    assert world.finish().state == "REVIEW_REQUIRED"                 # orphan found through inventory_page
    assert world.index.evidence_for("doc-0") is not None              # an orphan is reported, never deleted


def test_admin_members_are_unreachable_through_the_worker_view(world):
    view = world.options["index"]
    for name in ADMIN_MEMBERS:
        with pytest.raises(AttributeError):
            getattr(view, name)
    with pytest.raises(AttributeError):
        view.delete = lambda *a: None
