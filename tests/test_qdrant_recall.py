# ==========================================================
# Projet      : Eidolon Memory Engine
# Organisation: Eidolon Core Technologies (ECT)
# Fichier     : tests/test_qdrant_recall.py
# Description : Qdrant candidates through canonical policy and excerpt budgets.
# Standard    : Eidolon Presentation Standard v1
# ==========================================================
from dataclasses import replace

from core.retrieval.contextual import ContextualRecall
from tests.test_contextual_recall import backend, store, STAMP
from tests.test_qdrant_index import client, index


def test_qdrant_to_canonical_policy_and_bounded_excerpt(tmp_path, index):
    data = backend(tmp_path)
    store(data, 'old', status='SUPERSEDED')
    store(data, 'valid')
    index.rebuild(data.persistent_root)
    result = ContextualRecall(data, index=index).recall('power measurement',
        query_scope={'goal': 'efficiency'}, at=STAMP, max_items=1,
        max_chars=5, max_item_chars=5)
    assert result.items[0].information_id == 'valid'
    assert result.items[0].content == 'power'
    assert result.excluded_counts == {'SUPERSEDED': 1}
    assert result.items[0].ranking['index']['index_freshness'] == 'FULL_REBUILD_SNAPSHOT'


def test_qdrant_revision_lag_then_explicit_sync(tmp_path, index):
    data = backend(tmp_path)
    old = store(data, 'item')
    index.rebuild(data.persistent_root)
    data.update('item', replace(old, content='power corrected'), previous_revision=1)
    reader = ContextualRecall(data, index=index)
    stale = reader.recall('power')
    assert not stale.items and stale.excluded_counts == {'INDEX_REVISION_MISMATCH': 1}
    index.upsert(data.get('item'))
    current = reader.recall('power').items[0]
    assert current.revision == 2 and current.content == 'power corrected'
    assert current.ranking['index']['index_freshness'] == 'UNVERIFIED_INCREMENTAL'


def test_qdrant_orphan_and_pending_deletion_do_not_leak(tmp_path, index):
    data = backend(tmp_path)
    orphan = store(data, 'orphan')
    store(data, 'pending')
    index.rebuild(data.persistent_root)
    # Simulate a stale derived identity absent from the selected canonical root.
    (data.persistent_root / (orphan.information_id + '.md')).unlink()
    data.delete_request('pending', 'human', 'test', 1, 'delete')
    result = ContextualRecall(data, index=index).recall('power')
    assert not result.items
    assert result.excluded_counts == {'INDEX_MISSING_CANONICAL': 1, 'PENDING_DELETE': 1}
