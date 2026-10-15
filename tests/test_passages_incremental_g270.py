# ==========================================================
# Projet      : Eidolon Memory Engine
# Organisation: Eidolon Core Technologies (ECT)
# Fichier     : tests/test_passages_incremental_g270.py
# Description : Delta embeddings, complete snapshots, denial and activity interruption
# Standard    : Eidolon Presentation Standard v1
# ==========================================================
import pytest
from core.backend.models import Memory
from tests.test_qdrant_passages_g269 import index
from tests.test_archive_chunks import store_archive
from tests.test_contextual_recall import backend
from core.retrieval.contextual import ContextualRecall


def test_delta_reuses_old_vectors_and_recall_sees_new_source(tmp_path, index):
    data = backend(tmp_path); store_archive(data, ['V100 hardware.'])
    index.rebuild(data.persistent_root)
    before = index.active_generation(); calls = []; original = index.embed
    index.embed = lambda text: (calls.append(text), original(text))[1]
    data.store(Memory('new', content='New V100 cooling information.'))
    result = index.sync(data.persistent_root)
    assert result == {'state': 'PUBLISHED', 'embedded_documents': 1, 'copied_points': 1}
    assert calls == ['New V100 cooling information.']
    assert index.active_generation() != before
    bundle = ContextualRecall(data, index=index).recall('V100')
    assert bundle.index_status.state == 'INDEX_SNAPSHOT_MATCH'
    assert {i.information_id for i in bundle.items} == {'archive', 'new'}
    calls.clear()
    generation = index.active_generation()
    assert index.sync(data.persistent_root)['state'] == 'UNCHANGED'
    assert index.active_generation() == generation and calls == []


def test_mid_sync_failure_or_activity_keeps_complete_previous_alias(tmp_path, index):
    data = backend(tmp_path); store_archive(data, ['V100 hardware.'])
    index.rebuild(data.persistent_root); previous = index.active_generation()
    data.store(Memory('new', content='new information'))
    index.embed = lambda _: (_ for _ in ()).throw(OSError('unavailable'))
    with pytest.raises(OSError): index.sync(data.persistent_root)
    assert index.active_generation() == previous
    with pytest.raises(InterruptedError): index.sync(data.persistent_root, should_continue=lambda: False)
    assert index.active_generation() == previous
    with pytest.raises(PermissionError): index.sync(data.persistent_root, authorize=lambda ident: ident == 'archive')
    assert index.active_generation() == previous


def test_changed_archive_replaces_passages_without_old_candidates(tmp_path, index):
    data = backend(tmp_path); store_archive(data, ['V100 hardware.'])
    index.rebuild(data.persistent_root)
    from dataclasses import replace
    current = data.get('archive')
    data.update('archive', replace(current, content=current.content.replace('V100 hardware.', 'A different archive about cooling.')), previous_revision=current.revision)
    assert index.sync(data.persistent_root)['embedded_documents'] == 1
    assert index.status().points == 1
    assert ContextualRecall(data,index=index).recall('cooling').items[0].content == 'A different archive about cooling.'
