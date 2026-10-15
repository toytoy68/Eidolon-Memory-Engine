# ==========================================================
# Projet      : Eidolon Memory Engine
# Organisation: Eidolon Core Technologies (ECT)
# Fichier     : tests/test_recall_freshness_g242.py
# Description : Freshness diagnostics include empty and bounded semantic recall.
# Standard    : Eidolon Presentation Standard v1
# ==========================================================
from dataclasses import asdict, replace
import json

import pytest

from core.indexing import manifest as manifests
from core.retrieval.contextual import ContextualRecall
from tests.test_contextual_recall import backend, store
from tests.test_indexed_recall import Candidates, hit
from tests.test_qdrant_index import client, index  # noqa: F401


def test_full_snapshot_match_is_an_observation_not_a_relevance_claim(tmp_path, index):
    data = backend(tmp_path)
    store(data, 'one')
    index.rebuild(data.persistent_root)
    result = ContextualRecall(data, index=index).recall('power')
    status = asdict(result.index_status)
    assert status['state'] == 'INDEX_SNAPSHOT_MATCH'
    assert status['source_digest'] == status['canonical_digest'] == index.status().source_digest
    assert status['generation'] == index.active_generation()
    assert status['reason'] == 'FULL_SOURCE_DIGEST_MATCH'
    assert result.items[0].freshness == 'CANONICAL_AT_READ'


@pytest.mark.parametrize('change', ['add', 'update', 'delete', 'same_revision'])
def test_any_canonical_change_is_signalled_even_when_not_a_candidate(tmp_path, index, change):
    data = backend(tmp_path)
    original = store(data, 'one')
    index.rebuild(data.persistent_root)
    if change == 'add':
        store(data, 'two')
    elif change == 'update':
        data.update('one', replace(original, content='corrected'), previous_revision=1)
    elif change == 'delete':
        (data.persistent_root / 'one.md').unlink()
    else:
        path = data.persistent_root / 'one.md'
        path.write_bytes(path.read_bytes().replace(b'power measurement', b'other measurement'))
    result = ContextualRecall(data, index=index).recall('power')
    assert result.index_status.state == 'INDEX_STALE'
    assert result.index_status.reason == 'FULL_SOURCE_DIGEST_MISMATCH'
    assert result.index_status.source_digest != result.index_status.canonical_digest


def test_empty_index_still_reports_added_canonical_source(tmp_path, index):
    data = backend(tmp_path)
    index.rebuild(data.persistent_root)
    store(data, 'new')
    result = ContextualRecall(data, index=index).recall('power')
    assert result.items == ()
    assert result.index_status.state == 'INDEX_STALE'


def test_incremental_index_does_not_claim_a_full_snapshot(tmp_path, index):
    data = backend(tmp_path)
    memory = store(data, 'one')
    index.upsert(memory)
    result = ContextualRecall(data, index=index).recall('power')
    assert result.index_status.state == 'INDEX_UNVERIFIED'
    assert result.index_status.reason == 'NO_FULL_SOURCE_DIGEST'
    assert result.index_status.canonical_digest is None
    assert result.items


def test_generic_index_without_snapshot_is_explicitly_unverified(tmp_path):
    data = backend(tmp_path)
    store(data, 'one')
    result = ContextualRecall(data, index=Candidates([hit('one')])).recall('power')
    assert result.index_status.state == 'INDEX_UNVERIFIED'
    assert result.index_status.reason == 'SNAPSHOT_NOT_SUPPORTED'
    assert result.items
    assert ContextualRecall(data).recall('power').index_status is None


@pytest.mark.parametrize('limits', [dict(max_entries=1), dict(max_file_bytes=16), dict(max_total_bytes=16)])
def test_incomplete_bounded_diagnostic_never_claims_match(tmp_path, index, limits):
    data = backend(tmp_path)
    store(data, 'one')
    store(data, 'two')
    index.rebuild(data.persistent_root)
    budget = manifests.ManifestBudget(**limits)
    result = ContextualRecall(data, index=index, freshness_budget=budget).recall('power')
    assert result.index_status.state == 'INDEX_UNVERIFIED'
    assert result.index_status.reason == 'CANONICAL_CHECK_INCOMPLETE'
    assert result.index_status.canonical_digest is None
    # G243 also bounds proof reads; only that per-file refusal excludes hits.
    assert bool(result.items) == ('max_file_bytes' not in limits)
    assert str(tmp_path) not in json.dumps(asdict(result.index_status))


def test_freshness_is_recomputed_between_calls_and_preserved_in_payload(tmp_path, index):
    data = backend(tmp_path)
    store(data, 'one')
    index.rebuild(data.persistent_root)
    reader = ContextualRecall(data, index=index)
    assert reader.recall('power').index_status.state == 'INDEX_SNAPSHOT_MATCH'
    store(data, 'two')
    payload = reader.recall_payload('power', max_payload_chars=20000)
    assert json.loads(payload.text)['index_status']['state'] == 'INDEX_STALE'
    index.rebuild(data.persistent_root)
    assert reader.recall('power').index_status.state == 'INDEX_SNAPSHOT_MATCH'


def test_descriptor_changed_inside_query_is_refused(tmp_path, index, monkeypatch):
    data = backend(tmp_path)
    store(data, 'one')
    index.rebuild(data.persistent_root)
    real = index.client.query_points
    def changing(*args, **kwargs):
        result = real(*args, **kwargs)
        index._write_descriptor(index.active_generation(), None)
        return result
    monkeypatch.setattr(index.client, 'query_points', changing)
    with pytest.raises(ValueError, match='changed during query'):
        ContextualRecall(data, index=index).recall('power')


def test_empty_query_has_snapshot_without_embedding(tmp_path, index):
    data = backend(tmp_path)
    index.rebuild(data.persistent_root)
    def forbidden(_):
        raise AssertionError('empty query must not be embedded')
    index.embed = forbidden
    snapshot = index.query_snapshot('')
    assert snapshot.hits == ()
    assert snapshot.source_digest == manifests.build_manifest(data.persistent_root).digest


def test_bounded_manifest_matches_existing_digest_and_exact_byte_budget(tmp_path):
    data = backend(tmp_path)
    store(data, 'z')
    store(data, 'a')
    total = sum(p.stat().st_size for p in data.persistent_root.glob('*.md'))
    result = manifests.build_bounded_manifest(data.persistent_root,
        budget=manifests.ManifestBudget(max_total_bytes=total))
    assert result == manifests.build_manifest(data.persistent_root)
    with pytest.raises(ValueError):
        manifests.build_bounded_manifest(data.persistent_root,
            budget=manifests.ManifestBudget(max_total_bytes=total - 1))


@pytest.mark.parametrize('field', ['max_entries', 'max_file_bytes', 'max_total_bytes'])
@pytest.mark.parametrize('value', [True, 0, -1, 1.5, None])
def test_budget_rejects_invalid_configuration(field, value):
    with pytest.raises(ValueError):
        manifests.ManifestBudget(**{field: value})


def test_symlink_in_unselected_canonical_source_cannot_prove_complete(tmp_path, index):
    data = backend(tmp_path)
    index.rebuild(data.persistent_root)
    (data.persistent_root / 'unsafe.md').symlink_to(tmp_path / 'absent')
    from core.operations.errors import OperationConflict
    with pytest.raises(OperationConflict, match='readiness'):
        ContextualRecall(data, index=index).recall('power')
    with pytest.raises(ValueError):
        manifests.build_bounded_manifest(data.persistent_root)


def test_generation_swap_during_final_descriptor_check_is_refused(tmp_path, index, monkeypatch):
    data = backend(tmp_path)
    store(data, 'one')
    index.rebuild(data.persistent_root)
    generation = index.active_generation()
    descriptor = index._descriptor()
    replacement = index._generation()
    index._write_descriptor(replacement, descriptor['source_digest'])
    from qdrant_client import models
    real_query, real_descriptor = index.client.query_points, index._descriptor
    after_query = False
    calls = 0
    def query(*args, **kwargs):
        nonlocal after_query
        result = real_query(*args, **kwargs)
        after_query = True
        return result
    def observe():
        nonlocal calls
        value = real_descriptor()
        if after_query:
            calls += 1
            # active_generation performs the first descriptor read. Swap at
            # the following standalone descriptor check, after it has read.
            if calls == 2:
                index.client.update_collection_aliases([
                    models.DeleteAliasOperation(delete_alias=models.DeleteAlias(alias_name=index.alias)),
                    models.CreateAliasOperation(create_alias=models.CreateAlias(
                        collection_name=replacement, alias_name=index.alias))])
        return value
    monkeypatch.setattr(index.client, 'query_points', query)
    monkeypatch.setattr(index, '_descriptor', observe)
    with pytest.raises(ValueError, match='changed during query'):
        index.query('power')
    assert index.active_generation() != generation


def test_snapshot_contract_rejects_malformed_metadata_before_using_hits(tmp_path):
    from core.indexing.query_snapshot import IndexQuerySnapshot
    data = backend(tmp_path)
    store(data, 'one')
    class InvalidSnapshot(Candidates):
        def query_snapshot(self, *args, **kwargs):
            return self.snapshot
    candidate = InvalidSnapshot([])
    for malformed in [None, {}, IndexQuerySnapshot((), '../private', None),
                      IndexQuerySnapshot((), 'generation', 'wrong'),
                      IndexQuerySnapshot([hit('one')], 'generation', None),
                      IndexQuerySnapshot((hit('one'),) * 101, 'generation', None)]:
        candidate.snapshot = malformed
        with pytest.raises(ValueError, match='snapshot|batch'):
            ContextualRecall(data, index=candidate).recall('power')
    assert candidate.calls == []


def test_total_manifest_budget_bounds_second_read_before_overshoot(tmp_path, monkeypatch):
    from core.indexing.worker_canonical import CanonicalReader
    data = backend(tmp_path)
    store(data, 'a')
    store(data, 'b')
    first_size = (data.persistent_root / 'a.md').stat().st_size
    real = CanonicalReader.read_sized
    limits = []
    def measured(self, identity):
        limits.append((identity, self.max_bytes))
        return real(self, identity)
    monkeypatch.setattr(CanonicalReader, 'read_sized', measured)
    with pytest.raises(ValueError):
        manifests.build_bounded_manifest(data.persistent_root,
            budget=manifests.ManifestBudget(max_total_bytes=first_size + 10))
    assert limits == [('a', first_size + 10), ('b', 10)]
