# ==========================================================
# Projet      : Eidolon Memory Engine
# Organisation: Eidolon Core Technologies (ECT)
# Fichier     : tests/test_indexed_recall.py
# Description : Canonical policy must dominate optional index candidates.
# Standard    : Eidolon Presentation Standard v1
# ==========================================================
from dataclasses import replace

import pytest

from core.indexing.port import IndexHit
from core.retrieval.contextual import ContextualRecall
from tests.test_contextual_recall import backend, store, STAMP


class Candidates:
    def __init__(self, hits):
        self.hits = hits
        self.calls = []

    def query(self, text, *, limit):
        self.calls.append((text, limit))
        return self.hits


def hit(identity, revision=1, score=1.0):
    return IndexHit(identity, score, {'revision': revision, 'policy': 'synthetic',
                    'index_freshness': 'UNVERIFIED_INCREMENTAL'})


def recall(data, index, **options):
    return ContextualRecall(data, index=index).recall(
        'unrelated query', query_scope={'goal': 'efficiency'}, at=STAMP, **options)


def test_index_candidates_use_current_canonical_text_and_provenance(tmp_path):
    data = backend(tmp_path)
    memory = store(data, 'current', content='Canonical evidence')
    index = Candidates([hit('current')])
    result = recall(data, index)
    assert result.items[0].content == memory.content
    assert result.items[0].provenance == memory.provenance
    assert result.items[0].freshness == 'CANONICAL_AT_READ'
    assert 'index_candidate' in result.items[0].selection_reasons
    assert 'lexical_v1_candidate' not in result.items[0].selection_reasons
    assert result.items[0].ranking['policy'] == 'canonical-index-candidates/1'
    assert index.calls == [('unrelated query', 100)]


def test_missing_and_changed_revision_do_not_return_stale_evidence(tmp_path):
    data = backend(tmp_path)
    old = store(data, 'changed')
    data.update('changed', replace(old, content='New evidence'), previous_revision=1)
    store(data, 'valid')
    result = recall(data, Candidates([hit('gone'), hit('changed'), hit('valid')]), max_items=1)
    assert [i.information_id for i in result.items] == ['valid']
    assert result.excluded_counts == {'INDEX_MISSING_CANONICAL': 1, 'INDEX_REVISION_MISMATCH': 1}


def test_operational_filters_run_before_output_budget(tmp_path):
    data = backend(tmp_path)
    store(data, 'expired', until='2026-01-01T00:00:00Z')
    store(data, 'outside', scope={'goal': 'speed'})
    store(data, 'refuted', status='REFUTED')
    store(data, 'replaced', status='SUPERSEDED')
    store(data, 'pending')
    data.delete_request('pending', 'human', 'test', 1, 'delete')
    store(data, 'valid')
    result = recall(data, Candidates([hit(i) for i in
                    ['expired', 'outside', 'refuted', 'replaced', 'pending', 'valid']]),
                    max_items=1, max_chars=5, max_item_chars=5)
    assert result.items[0].information_id == 'valid'
    assert result.items[0].content == 'power'
    assert result.excluded_counts == {'EXPIRED': 1, 'OUT_OF_SCOPE': 1,
                    'REFUTED': 1, 'SUPERSEDED': 1, 'PENDING_DELETE': 1}


def test_historical_policy_remains_explicit(tmp_path):
    data = backend(tmp_path)
    store(data, 'old', status='REFUTED', until='2026-01-01T00:00:00Z')
    item = recall(data, Candidates([hit('old')]), mode='historical').items[0]
    assert item.needs_review and item.applicability == 'EXPIRED'
    assert 'historical_mode' in item.selection_reasons


def test_each_recall_rereads_canonical_even_with_same_index_revision(tmp_path):
    data = backend(tmp_path)
    store(data, 'item', content='original evidence')
    index = Candidates([hit('item')])
    reader = ContextualRecall(data, index=index)
    assert reader.recall('query').items[0].content == 'original evidence'
    path = data.persistent_root / 'item.md'
    path.write_bytes(path.read_bytes().replace(b'original evidence', b'modified evidence'))
    assert reader.recall('query').items[0].content == 'modified evidence'
    assert len(index.calls) == 2


def test_index_failure_is_not_silently_replaced_by_lexical_results(tmp_path):
    class Offline:
        def query(self, *args, **kwargs):
            raise ConnectionError('offline')
    data = backend(tmp_path)
    store(data, 'power')
    with pytest.raises(ConnectionError):
        recall(data, Offline())


@pytest.mark.parametrize('bad', [hit('../secret'), hit('item', True), hit('item', 0),
    hit('item', None), hit('item', score=float('nan')), hit('item', score=True),
    IndexHit('item', 1.0, {}), IndexHit('item', 1.0, None)])
def test_malformed_index_candidates_fail_closed(tmp_path, bad):
    data = backend(tmp_path)
    store(data, 'item')
    with pytest.raises(ValueError, match='candidate'):
        recall(data, Candidates([hit('item'), bad]))


def test_duplicate_id_is_not_returned_twice(tmp_path):
    data = backend(tmp_path)
    store(data, 'item')
    assert len(recall(data, Candidates([hit('item'), hit('item')])).items) == 1


@pytest.mark.parametrize('limit', [True, 0, 1001])
def test_candidate_limit_must_be_explicitly_bounded(tmp_path, limit):
    with pytest.raises(ValueError):
        ContextualRecall(backend(tmp_path), index=Candidates([]), candidate_limit=limit)


def test_oversized_index_result_is_rejected(tmp_path):
    index = Candidates([hit('item')] * 3)
    with pytest.raises(ValueError, match='candidate'):
        ContextualRecall(backend(tmp_path), index=index, candidate_limit=2).recall('query')


def test_pagination_uses_one_bounded_index_query(tmp_path):
    data = backend(tmp_path)
    for i in range(100):
        store(data, f'old-{i}', status='REFUTED')
    store(data, 'valid')
    index = Candidates([hit(f'old-{i}') for i in range(100)] + [hit('valid')])
    result = ContextualRecall(data, index=index, candidate_limit=101).recall('query', max_items=1)
    assert result.items[0].information_id == 'valid'
    assert result.excluded_counts == {'REFUTED': 100}
    assert index.calls == [('query', 101)]


def test_token_budget_still_applies(tmp_path):
    data = backend(tmp_path)
    store(data, 'item')
    result = recall(data, Candidates([hit('item')]), max_tokens=5, token_counter=len)
    assert result.items[0].content == 'power' and result.used_tokens == 5


@pytest.mark.parametrize('options', [{'max_chars': 0}, {'max_items': False}, {'max_tokens': 1}])
def test_invalid_budget_does_not_contact_index(tmp_path, options):
    index = Candidates([])
    with pytest.raises(ValueError):
        recall(backend(tmp_path), index, **options)
    assert index.calls == []


def test_default_lexical_recall_is_unchanged(tmp_path):
    data = backend(tmp_path)
    store(data, 'item')
    result = ContextualRecall(data).recall('power')
    assert result.items and 'lexical_v1_candidate' in result.items[0].selection_reasons
