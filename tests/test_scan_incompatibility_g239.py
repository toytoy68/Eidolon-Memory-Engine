# ==========================================================
# Projet      : Eidolon Memory Engine
# Organisation: Eidolon Core Technologies (ECT)
# Fichier     : tests/test_scan_incompatibility_g239.py
# Description : Preserve typed descriptor incompatibility through scans and controller.
# Standard    : Eidolon Presentation Standard v1
# ==========================================================
from datetime import timedelta
import pytest
from core.backend.models import Memory
from core.indexing.qdrant_index import _META, DOCUMENT_PROJECTION
from tests.test_index_maintenance import world


def projection(world, value):
    world.client.set_payload(world.index.alias, payload={'projection_id': value}, points=[_META], wait=True)


@pytest.mark.parametrize('kind', ['canonical', 'orphans', 'controller'])
@pytest.mark.parametrize('corruption', [{'projection_id': 'passage-v1'}, {'embedding_id': 'other'}, {'schema': 1}])
def test_persisted_incompatibility_is_not_reported_as_an_outage(world, kind, corruption):
    seq = world.write(published=False)
    cycle = world.cycle()
    world.client.set_payload(world.index.alias, payload=corruption, points=[_META], wait=True)
    if kind == 'controller':
        result = world.tick()
        assert world.cycle().status().detail['last_result']['state'] == 'INDEX_INCOMPATIBLE'
        assert world.tick().state == 'WAITING'
    else:
        result = getattr(cycle, kind).run_page(limit=2)
    assert result.state == 'INDEX_INCOMPATIBLE'
    assert world.journal.intent(seq).state == 'INTENT'
    world.client.set_payload(world.index.alias, payload={'projection_id': DOCUMENT_PROJECTION,
        'embedding_id': 'synthetic-v1', 'schema': 2}, points=[_META], wait=True)
    world.at += timedelta(seconds=30)
    assert world.finish().state == 'CYCLE_COMPLETE'


def test_canonical_partial_page_retains_safe_prefix_and_retries_uncertain_row(world, monkeypatch):
    world.write('a', intent=False)
    world.write('b', intent=False)
    scan = world.cycle().canonical
    original = world.index.evidence_for
    def corrupt_second(ident):
        if ident == 'b':
            projection(world, 'passage-v1')
        return original(ident)
    monkeypatch.setattr(world.index, 'evidence_for', corrupt_second)
    result = scan.run_page(limit=2)
    assert result.state == 'INDEX_INCOMPATIBLE' and result.cursor == 1
    assert len(result.queued) == 1 and world.journal.pending()[0].information_id == 'a'
    monkeypatch.setattr(world.index, 'evidence_for', original)
    projection(world, DOCUMENT_PROJECTION)
    result = world.cycle().canonical.run_page(limit=2)
    assert result.cursor == 2 and len(result.queued) == 1
    assert [row.information_id for row in world.journal.pending()] == ['a', 'b']


def test_orphan_incompatibility_discards_partial_observation_page(world, monkeypatch):
    for ident in ('orphan_a', 'orphan_b'):
        world.index.upsert_verified(Memory(ident, content='synthetic'), canonical_sha256='a'*64)
    scan = world.cycle().orphans
    original = world.index.evidence_for
    seen = []
    def corrupt_second(ident):
        seen.append(ident)
        if len(seen) == 2:
            projection(world, 'passage-v1')
        return original(ident)
    monkeypatch.setattr(world.index, 'evidence_for', corrupt_second)
    result = scan.run_page(limit=3)
    assert result.state == 'INDEX_INCOMPATIBLE' and result.inspected == result.review_count == 0
    monkeypatch.setattr(world.index, 'evidence_for', original)
    projection(world, DOCUMENT_PROJECTION)
    result = world.cycle().orphans.run_page(limit=3)
    assert result.state == 'EXHAUSTED' and result.inspected == result.review_count == 2
    assert world.index.status().documents == 2


def test_orphan_review_returns_no_candidates_on_incompatible_descriptor(world):
    world.index.upsert_verified(Memory('orphan', content='synthetic'), canonical_sha256='a'*64)
    scan = world.cycle().orphans
    assert scan.run_page(limit=2).state == 'EXHAUSTED'
    projection(world, 'passage-v1')
    review = world.cycle().orphans.review_page()
    assert review.state == 'INDEX_INCOMPATIBLE' and review.items == ()
    projection(world, DOCUMENT_PROJECTION)
    review = world.cycle().orphans.review_page()
    assert len(review.items) == 1 and review.items[0].state == 'DELETE_CANDIDATE'


def test_final_snapshot_incompatibility_cannot_finish_canonical_scan(world, monkeypatch):
    world.write(intent=False)
    scan = world.cycle().canonical
    assert scan.run_page().state == 'VERIFYING'
    original = scan._snapshot
    def changed():
        result = original()
        projection(world, 'passage-v1')
        return result
    monkeypatch.setattr(scan, '_snapshot', changed)
    assert scan.run_page().state == 'INDEX_INCOMPATIBLE'
    projection(world, DOCUMENT_PROJECTION)
    assert world.cycle().canonical.run_page().state == 'COMPLETE'


@pytest.mark.parametrize('kind', ['canonical', 'orphans', 'controller'])
def test_transport_failure_remains_unavailable(world, monkeypatch, kind):
    cycle = world.cycle()
    def unavailable():
        raise ConnectionError('synthetic transport outage')
    monkeypatch.setattr(world.index, 'active_generation', unavailable)
    result = world.tick() if kind == 'controller' else getattr(cycle, kind).run_page()
    assert result.state == 'INDEX_UNAVAILABLE'
