# ==========================================================
# Projet      : Eidolon Memory Engine
# Organisation: Eidolon Core Technologies (ECT)
# Fichier     : tests/test_index_projection.py
# Description : Projection identity through real Markdown, journal and Qdrant.
# Standard    : Eidolon Presentation Standard v1
# ==========================================================
import pytest
from core.backend.models import Memory
from core.indexing.qdrant_index import QdrantIndex, _META, _point_id
from tests.test_worker_journal import world

PROJECTION = "information-content-json-v1"


def descriptor(world):
    return world.client.retrieve(world.index.alias, ids=[_META])[0].payload


def corrupt(world, **fields):
    world.client.set_payload(world.index.alias, payload=fields, points=[_META], wait=True)


def test_new_descriptor_identifies_whole_document_projection(world):
    data = descriptor(world)
    assert data["schema"] == 2
    assert data["projection_id"] == PROJECTION


@pytest.mark.parametrize("fields", [{"schema": 1}, {"projection_id": None},
    {"projection_id": "passage-v1"}, {"embedding_id": "other"}])
@pytest.mark.parametrize("published", [False, True])
def test_incompatible_descriptor_stops_journal_before_any_effect(world, fields, published):
    seq = world.write(published=published)
    corrupt(world, **fields)
    before = descriptor(world).copy()
    result = world.worker().run_once()
    assert result.status == "INDEX_INCOMPATIBLE"
    assert not result.published and not result.indexed
    assert world.states() == {seq: "PUBLISHED" if published else "INTENT"}
    assert world.writes == 0 and descriptor(world) == before


@pytest.mark.parametrize("method", ["status", "query", "revision_for", "evidence_for",
                                    "upsert", "upsert_verified", "delete", "rebuild", "inventory_page"])
def test_incompatible_projection_refuses_every_index_entrypoint(world, method):
    world.write()
    generation = world.index.active_generation()
    corrupt(world, projection_id="passage-v1")
    before = world.client.scroll(generation, limit=100, with_vectors=True)
    args = {"status": (), "query": ("source",), "revision_for": ("doc",),
        "evidence_for": ("doc",), "upsert": (Memory("other", content="text"),),
        "upsert_verified": (Memory("other", content="text"),), "delete": ("doc",),
        "rebuild": (world.root,), "inventory_page": ()}
    kwargs = {"upsert_verified": {"canonical_sha256": "a"*64},
              "inventory_page": {"generation": generation}}
    with pytest.raises(ValueError):
        getattr(world.index, method)(*args[method], **kwargs.get(method, {}))
    assert world.client.scroll(generation, limit=100, with_vectors=True) == before


def test_legacy_descriptor_is_not_silently_relabelled_on_reopen(world):
    corrupt(world, schema=1)
    before = descriptor(world).copy()
    with pytest.raises(ValueError):
        QdrantIndex(world.client, world.index.alias, embed=lambda _: [1., 0.],
                    dimensions=2, embedding_id="synthetic-v1", create=True)
    assert descriptor(world) == before


@pytest.mark.parametrize("method", ["upsert", "upsert_verified", "rebuild", "query"])
def test_projection_changed_during_embedding_is_not_overwritten_or_published(world, method):
    world.write()
    generation = world.index.active_generation()
    def changed(_):
        corrupt(world, projection_id="passage-v1")
        return [1., 0.]
    world.index.embed = changed
    args = {"upsert": (Memory("doc", content="text"),),
            "upsert_verified": (Memory("doc", content="text"),),
            "rebuild": (world.root,), "query": ("source",)}
    with pytest.raises(ValueError):
        getattr(world.index, method)(*args[method], **({"canonical_sha256": "a"*64}
                                                     if method == "upsert_verified" else {}))
    assert descriptor(world)["projection_id"] == "passage-v1"
    assert world.index._active_generation() == generation
    assert world.client.retrieve(generation, ids=[_point_id("doc")]) == []


@pytest.mark.parametrize("value", [None, "passage-v1"])
@pytest.mark.parametrize("method", ["evidence_for", "inventory_page"])
def test_verified_point_with_wrong_projection_is_never_evidence(world, value, method):
    world.write()
    world.worker().run_once()
    generation = world.index.active_generation()
    world.client.set_payload(generation, payload={"projection_id": value},
                             points=[_point_id("doc")], wait=True)
    with pytest.raises(ValueError):
        if method == "evidence_for":
            world.index.evidence_for("doc")
        else:
            world.index.inventory_page(generation=generation)


def test_descriptor_outage_blocks_even_intent_recovery_then_recovers(world, monkeypatch):
    seq = world.write(published=False)
    original = world.index.active_generation
    def offline():
        raise ConnectionError("offline")
    monkeypatch.setattr(world.index, "active_generation", offline)
    assert world.worker().run_once().status == "INDEX_UNAVAILABLE"
    assert world.states() == {seq: "INTENT"}
    monkeypatch.setattr(world.index, "active_generation", original)
    assert world.worker().run_once().published == (seq,)
    assert world.worker().run_once().indexed == (seq,)


def test_canonical_change_inside_authorization_prevents_stale_effect(world):
    first = world.write()
    worker = world.worker()
    calls = []
    def allowed(*args):
        calls.append(args)
        if len(calls) == 2:  # public apply_upsert authorization, after its first read
            world.write(revision=2)
        return True
    worker.authorize = allowed
    result = worker.run_once()
    assert not result.indexed and world.writes == 0
    assert world.states()[first] == "PUBLISHED"


def test_rights_revoked_before_action_prevents_effect(world):
    seq = world.write()
    worker = world.worker()
    calls = []
    def allowed(*args):
        calls.append(args)
        return len(calls) == 1
    worker.authorize = allowed
    assert not worker.run_once().indexed
    assert world.states() == {seq: "PUBLISHED"} and world.writes == 0


def test_mid_page_incompatible_row_does_not_advance_cursor(world, monkeypatch):
    seq = world.write()
    original = world.index.evidence_for
    def changed(ident):
        corrupt(world, projection_id="passage-v1")
        return original(ident)
    monkeypatch.setattr(world.index, "evidence_for", changed)
    page = world.worker().run_page()
    assert page.status == "INDEX_INCOMPATIBLE"
    assert page.after == 0 and not page.exhausted
    assert world.states() == {seq: "PUBLISHED"} and world.writes == 0


def test_missing_intent_before_publication_stays_for_review_at_any_age(world):
    seq = world.journal.begin("missing", 1, "UPSERT", "a"*64)
    created = world.journal.pending()[0].created
    for now in (created + 100, created + 1000):
        report = world.worker().run_once(now=now)
        assert report.deferred == ((seq, "UNVERIFIED"),)
        assert world.states() == {seq: "INTENT"} and world.writes == 0
