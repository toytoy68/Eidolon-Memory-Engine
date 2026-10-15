# ==========================================================
# Projet      : Eidolon Memory Engine
# Organisation: Eidolon Core Technologies (ECT)
# Fichier     : tests/test_qdrant_server_maintenance_g238.py
# Description : Real HTTP, disk restart and bounded maintenance on an owned server.
# Standard    : Eidolon Presentation Standard v1
# ==========================================================
from datetime import datetime, timedelta, timezone
from uuid import uuid4
import pytest
from core.backend.filesystem import FilesystemBackend
from core.backend.models import Memory
from core.indexing.change_journal import ChangeJournal
from core.indexing.maintenance import IndexMaintenance
from core.indexing.worker_canonical import CanonicalReader
from core.indexing.worker_journal import JournalUpsertWorker
from tests.qdrant_server_fixture import qdrant_server

qdrant = pytest.importorskip('qdrant_client')
from core.indexing.qdrant_index import QdrantIndex, _META


@pytest.fixture
def world(tmp_path, qdrant_server):
    class World:
        def __init__(self):
            self.base = tmp_path
            self.root = tmp_path/'persistent'
            self.backend = FilesystemBackend(self.root, tmp_path/'history')
            self.journal = ChangeJournal(tmp_path/'changes.sqlite3')
            self.server = qdrant_server
            self.alias = 'eidolon_server_' + uuid4().hex
            self.writes = 0
            self.allowed = True
            self.at = datetime.now(timezone.utc).replace(hour=3, minute=0, second=0, microsecond=0)+timedelta(days=1)
            self.open(create=True)

        def open(self, create=False):
            self.client = self.server.client()
            self.index = QdrantIndex(self.client, self.alias, embed=self.embed,
                dimensions=2, embedding_id='server-synthetic-v1', create=create)
            self.options = dict(canonical_root=self.root, index=self.index,
                authorize=lambda *a: self.allowed, profile_id='owner', expected_profile_id='owner',
                expected_model_id='server-synthetic-v1')

        def embed(self, text):
            self.writes += 1
            return [1., 0.]

        def write(self, ident='doc', published=True, content='synthetic'):
            self.backend.store(Memory(ident, content=content))
            _, digest = CanonicalReader(self.root)(ident)
            seq = self.journal.begin(ident, 1, 'UPSERT', digest)
            if published:
                self.journal.published(seq)
            return seq

        def cycle(self, **kwargs):
            options = dict(canonical_checkpoint=self.base/'canonical.sqlite3',
                orphan_checkpoint=self.base/'orphans.sqlite3', page_size=2, pending_limit=2, **self.options)
            options.update(kwargs)
            return IndexMaintenance(self.base/'cycle.sqlite3', self.journal, **options)

        def tick(self, **kwargs):
            return self.cycle(**kwargs).tick(at=self.at, last_activity=self.at-timedelta(hours=1),
                boot_at=self.at-timedelta(hours=2), load_ok=True)

        def finish(self, **kwargs):
            for _ in range(400):
                result = self.tick(**kwargs)
                if result.state in ('CYCLE_COMPLETE', 'REVIEW_REQUIRED'):
                    return result
                assert result.state in ('ACTIVE', 'RESTART_REQUIRED'), result
            pytest.fail('server cycle did not finish')

        def restart(self, crash=False):
            self.client.close()
            self.server.stop(crash=crash)
            self.server.start()
            self.open()

    w = World()
    yield w
    w.client.close()


def test_http_maintenance_converges_and_rebuild_preserves_proofs(world):
    for i in range(5):
        world.write(str(i), published=False)
    assert world.finish().state == 'CYCLE_COMPLETE'
    assert world.writes == 5 and world.journal.pending() == ()
    old = world.index.active_generation()
    world.index.rebuild(world.root)
    new = world.index.active_generation()
    assert new != old and world.writes == 10
    world.at += timedelta(minutes=10)
    assert world.finish().state == 'CYCLE_COMPLETE'
    assert world.writes == 10  # no duplicate maintenance embedding after rebuild
    assert world.client.collection_exists(old)
    world.restart()
    assert world.index.active_generation() == new
    assert world.index.status().documents == 5
    assert world.cycle().status().state == 'CYCLE_COMPLETE'


@pytest.mark.parametrize('crash', [False, True])
def test_lost_ack_and_server_restart_adopt_point_without_reembedding(world, monkeypatch, crash):
    seq = world.write()
    original = world.index.upsert_verified
    def lose_ack(*args, **kwargs):
        original(*args, **kwargs)  # real wait=True HTTP response already received
        raise ConnectionError('simulated lost response after server acknowledgement')
    monkeypatch.setattr(world.index, 'upsert_verified', lose_ack)
    assert JournalUpsertWorker(world.journal, **world.options).run_once().status == 'INDEX_UNAVAILABLE'
    assert world.journal.intent(seq).state == 'PUBLISHED' and world.writes == 1
    world.restart(crash=crash)
    result = JournalUpsertWorker(world.journal, **world.options).run_once()
    assert result.indexed == (seq,) and world.writes == 1
    assert world.index.evidence_for('doc').information_id == 'doc'


def test_actual_http_outage_defers_then_retries_same_pending_work(world):
    seq = world.write()
    world.server.stop()
    result = world.tick()
    assert result.state == 'INDEX_UNAVAILABLE'
    assert world.journal.intent(seq).state == 'PUBLISHED'
    world.server.start()
    world.at += timedelta(seconds=30)
    assert world.finish().state == 'CYCLE_COMPLETE'
    assert world.writes == 1


def test_server_descriptor_incompatibility_never_publishes_intent(world):
    seq = world.write(published=False)
    world.client.set_payload(world.alias, payload={'projection_id': 'passage-v1'}, points=[_META], wait=True)
    result = JournalUpsertWorker(world.journal, **world.options).run_once()
    assert result.status == 'INDEX_INCOMPATIBLE'
    assert world.journal.intent(seq).state == 'INTENT' and world.writes == 0
    assert world.tick().state == 'INDEX_INCOMPATIBLE'
    assert world.journal.intent(seq).state == 'INTENT' and world.writes == 0


def test_server_budget_and_orphan_review_never_delete(world):
    for i in range(3):
        world.write(str(i))
    world.index.upsert_verified(Memory('orphan', content='synthetic'), canonical_sha256='a'*64)
    result = world.finish(max_points=4)
    assert result.state == 'REVIEW_REQUIRED' and result.detail['orphan_review'] == 1
    assert world.index.status().documents == 4
    reviews = world.cycle(max_points=4).orphans.review_page(limit=10)
    assert any(row.information_id == 'orphan' for row in reviews.items)
    world.restart()
    assert world.index.status().documents == 4


def test_server_incomplete_inventory_does_not_report_completion(world):
    for i in range(3):
        world.write(str(i))
    result = world.finish(max_points=2)
    assert result.state == 'REVIEW_REQUIRED' and result.detail['orphan_review'] >= 1
    assert world.index.status().documents == 3


def test_server_oversized_document_stays_pending_while_tail_is_indexed(world):
    bad = world.write('large', content='x'*4096)
    good = world.write('small')
    result = world.finish(max_file_bytes=2048)
    assert result.state == 'REVIEW_REQUIRED'
    assert world.journal.intent(bad).state == 'PUBLISHED'
    assert world.journal.intent(good).state == 'INDEXED'
    assert world.writes == 1 and world.index.status().documents == 1


def test_clock_recovery_survives_server_restart_and_defers_effect_until_tick(world):
    world.write()
    correct = world.at
    world.at += timedelta(days=365)
    assert world.tick().state == 'ACTIVE'
    previous = world.at.timestamp()
    world.at = correct
    assert world.tick().state == 'CLOCK_REVERSED'
    world.restart()
    assert world.cycle().status().state == 'REVIEW_REQUIRED'
    receipt = world.cycle().recover_clock(at=correct, expected_last_at=previous, expected_cycle=1,
        actor='server-test', reason='synthetic clock correction', request_id='server-reset')
    assert receipt['cycle'] == 2 and world.writes == 0
    assert world.finish().state == 'CYCLE_COMPLETE' and world.writes == 1
