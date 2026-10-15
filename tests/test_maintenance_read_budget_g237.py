# ==========================================================
# Projet      : Eidolon Memory Engine
# Organisation: Eidolon Core Technologies (ECT)
# Fichier     : tests/test_maintenance_read_budget_g237.py
# Description : Shared controller read policy and durable oversized-row review.
# Standard    : Eidolon Presentation Standard v1
# ==========================================================
from datetime import timedelta
import pytest
from core.backend.models import Memory
from core.indexing.worker_canonical import CanonicalReader
from tests.test_index_maintenance import world


def test_controller_uses_same_bound_for_worker_and_scanner_and_binds_policy(world):
    cycle = world.cycle(max_file_bytes=1024)
    assert cycle.worker.reader.max_bytes == cycle.canonical.reader.max_bytes == 1024
    with pytest.raises(ValueError, match='context'):
        world.cycle(max_file_bytes=2048)
    assert world.cycle(max_file_bytes=1024).status().cycle == 1


def test_oversized_pending_document_is_reported_without_starving_good_work(world):
    world.backend.store(Memory('large', content='x'*4096))
    _, digest = CanonicalReader(world.root)('large')
    seq = world.journal.begin('large', 1, 'UPSERT', digest)
    world.journal.published(seq)
    good = world.write('small')
    for _ in range(100):
        result = world.cycle(max_file_bytes=2048).tick(at=world.at,
            last_activity=world.at-timedelta(hours=1), boot_at=world.at-timedelta(hours=2), load_ok=True)
        if result.state == 'REVIEW_REQUIRED':
            break
    assert result.state == 'REVIEW_REQUIRED'
    assert world.journal.intent(good).state == 'INDEXED'
    assert world.journal.intent(seq).state == 'PUBLISHED'
    assert world.cycle(max_file_bytes=2048).reviews()['items'][0]['reason'] == 'CANONICAL_TOO_LARGE'
    assert world.index.status().documents == 1


@pytest.mark.parametrize('value', [None, True, 0, -1, 1.5, 2**64])
def test_invalid_read_budgets_fail_before_checkpoint_creation(world, value):
    with pytest.raises(ValueError):
        world.cycle(max_file_bytes=value)
    assert not (world.base/'cycle.sqlite3').exists()
