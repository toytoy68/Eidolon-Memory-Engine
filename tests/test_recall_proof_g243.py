# ==========================================================
# Projet      : Eidolon Memory Engine
# Organisation: Eidolon Core Technologies (ECT)
# Fichier     : tests/test_recall_proof_g243.py
# Description : Candidate proof must match the actual canonical bytes cited.
# Standard    : Eidolon Presentation Standard v1
# ==========================================================
from dataclasses import replace

import pytest

from core.indexing.qdrant_index import _point_id
from core.indexing.manifest import ManifestBudget
from core.retrieval.contextual import ContextualRecall
from tests.test_contextual_recall import backend, store
from tests.test_qdrant_index import client, index  # noqa: F401


def test_same_revision_drift_never_reuses_verified_semantic_score(tmp_path, index):
    data = backend(tmp_path)
    store(data, 'one', content='power measurement')
    index.rebuild(data.persistent_root)
    path = data.persistent_root / 'one.md'
    path.write_bytes(path.read_bytes().replace(b'power measurement', b'other measurement'))
    result = ContextualRecall(data, index=index).recall('power')
    assert result.items == ()
    assert result.excluded_counts == {'INDEX_DIGEST_MISMATCH': 1}
    assert result.index_status.state == 'INDEX_STALE'


def test_provenance_is_carried_to_the_selected_canonical_excerpt(tmp_path, index):
    data = backend(tmp_path)
    store(data, 'one')
    index.rebuild(data.persistent_root)
    proof = index.evidence_for('one')
    item = ContextualRecall(data, index=index).recall('power').items[0]
    ranking = item.ranking['index']
    assert ranking['canonical_sha256'] == proof.canonical_sha256
    assert ranking['generation'] == proof.generation
    assert ranking['projection_id'] == 'information-content-json-v1'
    assert item.content == data.get('one').content


@pytest.mark.parametrize('field,bad', [
    ('canonical_sha256', 'broken'), ('canonical_sha256', None),
    ('embedding_id', 'different-model'), ('generation', 'different-generation'),
    ('projection_id', 'different-projection')])
def test_malformed_or_foreign_point_proof_is_refused(tmp_path, index, field, bad):
    data = backend(tmp_path)
    store(data, 'one')
    index.rebuild(data.persistent_root)
    index.client.set_payload(index.alias, {field: bad}, points=[_point_id('one')], wait=True)
    with pytest.raises(ValueError, match='proof'):
        ContextualRecall(data, index=index).recall('power')


def test_partial_point_proof_is_not_silently_downgraded_to_legacy(tmp_path, index):
    data = backend(tmp_path)
    store(data, 'one')
    index.rebuild(data.persistent_root)
    index.client.delete_payload(index.alias, keys=['canonical_sha256'], points=[_point_id('one')], wait=True)
    with pytest.raises(ValueError, match='proof'):
        index.query('power')


def test_unverified_legacy_upsert_remains_explicitly_unverified(tmp_path, index):
    data = backend(tmp_path)
    memory = store(data, 'one')
    index.upsert(memory)
    result = ContextualRecall(data, index=index).recall('power')
    assert result.items[0].content == memory.content
    assert result.index_status.state == 'INDEX_UNVERIFIED'
    assert 'canonical_sha256' not in result.items[0].ranking['index']


def test_verified_candidate_too_large_for_proof_read_is_not_cited(tmp_path, index):
    data = backend(tmp_path)
    store(data, 'one')
    index.rebuild(data.persistent_root)
    result = ContextualRecall(data, index=index, freshness_budget=ManifestBudget(max_file_bytes=16)).recall('power')
    assert not result.items
    assert result.excluded_counts == {'INDEX_CANONICAL_UNVERIFIED': 1}
    assert result.index_status.state == 'INDEX_UNVERIFIED'


def test_mismatch_does_not_hide_a_healthy_later_candidate(tmp_path, index):
    data = backend(tmp_path)
    store(data, 'a')
    store(data, 'b')
    index.rebuild(data.persistent_root)
    path = data.persistent_root / 'a.md'
    path.write_bytes(path.read_bytes().replace(b'power measurement', b'other measurement'))
    result = ContextualRecall(data, index=index).recall('power', max_items=1)
    assert [item.information_id for item in result.items] == ['b']
    assert result.excluded_counts == {'INDEX_DIGEST_MISMATCH': 1}


def test_all_proof_fields_removed_cannot_keep_full_rebuild_claim(tmp_path, index):
    data = backend(tmp_path)
    store(data, 'one')
    index.rebuild(data.persistent_root)
    index.client.delete_payload(index.alias,
        keys=['canonical_sha256', 'embedding_id', 'generation', 'projection_id'],
        points=[_point_id('one')], wait=True)
    with pytest.raises(ValueError, match='proof'):
        index.query('power')


def test_changed_source_between_backend_read_and_proof_read_is_excluded(tmp_path, index, monkeypatch):
    from core.indexing.worker_canonical import CanonicalReader
    data = backend(tmp_path)
    store(data, 'one')
    index.rebuild(data.persistent_root)
    original = CanonicalReader.__call__
    def changing(reader, identity):
        path = data.persistent_root / 'one.md'
        path.write_bytes(path.read_bytes().replace(b'power measurement', b'other measurement'))
        return original(reader, identity)
    monkeypatch.setattr(CanonicalReader, '__call__', changing)
    result = ContextualRecall(data, index=index).recall('power')
    assert not result.items
    assert result.excluded_counts == {'INDEX_DIGEST_MISMATCH': 1}
