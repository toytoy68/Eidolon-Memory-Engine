# ==========================================================
# Projet      : Eidolon Memory Engine
# Organisation: Eidolon Core Technologies (ECT)
# Fichier     : tests/test_qdrant_http_recovery_g240.py
# Description : Actual lost HTTP responses and large server-backed journal backlog.
# Standard    : Eidolon Presentation Standard v1
# ==========================================================
from datetime import timedelta
import pytest
from core.indexing.worker_journal import JournalUpsertWorker
from core.indexing.qdrant_index import QdrantIndex
from tests.qdrant_server_fixture import qdrant_server
from tests.test_qdrant_server_maintenance_g238 import world
from tests.qdrant_response_proxy import drop_point_response


@pytest.mark.parametrize('mode', ['disconnect', 'timeout'])
def test_real_response_loss_after_server_write_recovers_without_second_embedding(world, mode):
    seq = world.write()
    with drop_point_response(world.server, mode=mode) as proxy:
        client = proxy.client()
        try:
            index = QdrantIndex(client, world.alias, embed=world.embed, dimensions=2,
                                embedding_id='server-synthetic-v1')
            worker = JournalUpsertWorker(world.journal, **dict(world.options, index=index))
            proxy.armed = True
            result = worker.run_once()
            proxy.release.set()
            assert result.status == 'INDEX_UNAVAILABLE'
            assert proxy.dropped == 1 and proxy.acknowledged
            assert world.journal.intent(seq).state == 'PUBLISHED'
            assert world.index.evidence_for('doc') is not None  # direct connection, actual server write
            assert world.writes == 1
            assert worker.run_once().indexed == (seq,)
            assert world.writes == 1
        finally:
            client.close()


def test_1200_server_documents_converge_once_and_survive_restart(world):
    for i in range(1200):
        world.write(f'doc-{i:04d}')
    result = world.finish(page_size=100, pending_limit=100)
    assert result.state == 'CYCLE_COMPLETE'
    assert world.writes == 1200 and world.journal.pending() == ()
    assert world.index.status().documents == 1200
    world.restart()
    assert world.index.status().documents == 1200
    assert world.cycle(page_size=100, pending_limit=100).status().state == 'CYCLE_COMPLETE'
    assert JournalUpsertWorker(world.journal, **world.options).run_once().indexed == ()
    assert world.writes == 1200


def test_actual_mid_page_outage_keeps_uncertain_cursor_and_healthy_prefix(world, monkeypatch):
    first, second = world.write('a'), world.write('b')
    worker = JournalUpsertWorker(world.journal, **world.options)
    original = world.index.upsert_verified
    def stop_before_second(memory, **kwargs):
        if memory.information_id == 'b':
            world.server.stop()
        return original(memory, **kwargs)
    monkeypatch.setattr(world.index, 'upsert_verified', stop_before_second)
    page = worker.run_page(limit=2)
    assert page.status == 'INDEX_UNAVAILABLE' and not page.exhausted
    assert page.after == first and page.through == second
    assert page.result.indexed == (first,)
    assert world.journal.intent(second).state == 'PUBLISHED'
    world.server.start()
    monkeypatch.setattr(world.index, 'upsert_verified', original)
    page = worker.run_page(after=page.after, through=page.through, limit=2)
    assert page.exhausted and page.result.indexed == (second,)
    assert world.writes == 2 and world.index.status().documents == 2
