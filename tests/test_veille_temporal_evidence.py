# ==========================================================
# Projet      : Eidolon Memory Engine
# Organisation: Eidolon Core Technologies (ECT)
# Fichier     : tests/test_veille_temporal_evidence.py
# Description : Evidence dates survive excerpting, reopening and contextual recall
# Standard    : Eidolon Presentation Standard v1
# ==========================================================
"""Hindsight-inspired contracts; no upstream code or LLM truth scoring."""
import json

import pytest

from core.backend.filesystem import FilesystemBackend
from core.backend.models import Memory
from core.retrieval.contextual import ContextualRecall
from core.retrieval.payload import render


def backend(root):
    return FilesystemBackend(root / 'memory/persistent', root / 'memory/history')


def memory(identity='dated', **changes):
    values = dict(content='Inscription atelier : hier, inscription confirmée.',
                  metadata={'epistemic_status': 'CONFIRMED',
                            'context': {'scope': {'project': 'atelier'}}},
                  provenance={'source': 'synthetic-statement', 'timestamp': '2026-07-03T09:00:00+02:00'},
                  temporal={'created_at': '2026-10-21T12:00:00Z',
                            'observed_at': '2026-07-02T10:00:00+02:00'})
    values.update(changes)
    return Memory(identity, **values)


def recall(data, at, **kwargs):
    return ContextualRecall(data).recall('inscription atelier',
        query_scope={'project': 'atelier'}, at=at, **kwargs)


@pytest.mark.parametrize('at', ['2026-10-21T12:00:00Z', '2026-11-02T12:00:00+01:00'])
def test_query_date_never_replaces_statement_event_or_import_date(tmp_path, at):
    data = backend(tmp_path)
    original = memory()
    data.store(original)
    # Reopen on disk and trim the excerpt: dates must travel with that exact source.
    bundle = recall(backend(tmp_path), at, max_item_chars=20)
    payload = json.loads(render(bundle, max_payload_chars=20000).text)
    item = payload['items'][0]
    assert item['truncated'] is True
    assert item['provenance'] == original.provenance
    assert item['temporal'] == original.temporal
    assert payload['at'] == at
    assert item['information_id'] == original.information_id and item['revision'] == 1
    assert data.get(original.information_id) == original


def test_missing_source_date_is_not_filled_from_ingestion_or_question(tmp_path):
    data = backend(tmp_path)
    original = memory(provenance={'source': 'undated-import'},
                      temporal={'created_at': '2026-10-21T12:00:00Z'})
    data.store(original)
    item = recall(data, '2026-11-02T12:00:00Z').items[0]
    assert item.provenance == original.provenance
    assert item.temporal == original.temporal
    # Applicability MATCH is deliberately not a date-resolution or truth verdict.
    assert item.content == original.content


@pytest.mark.parametrize('at,expected', [
    ('2026-10-25T02:30:00+02:00', ['summer']),
    ('2026-10-25T02:30:00+01:00', ['winter']),
])
def test_repeated_local_hour_uses_offsets_before_selecting_evidence(tmp_path, at, expected):
    data = backend(tmp_path)
    data.store(memory('summer', temporal={'valid_from': '2026-10-25T00:00:00Z',
                                         'valid_until': '2026-10-25T00:59:59Z'}))
    data.store(memory('winter', temporal={'valid_from': '2026-10-25T01:00:00Z',
                                         'valid_until': '2026-10-25T01:59:59Z'}))
    assert [x.information_id for x in recall(data, at).items] == expected


def test_conflicting_current_values_remain_distinct_review_items(tmp_path):
    data = backend(tmp_path)
    for identity, number in [('first', 71), ('second', 67)]:
        data.store(memory(identity, content=f'Inscription atelier : {number} places.',
            metadata={'epistemic_status': 'CONFLICTED', 'context': {'scope': {'project': 'atelier'}}}))
    items = recall(data, '2026-11-02T12:00:00Z').items
    assert {x.information_id for x in items} == {'first', 'second'}
    assert all(x.needs_review and x.applicability == 'UNRESOLVED' for x in items)


def test_historical_recall_labels_superseded_source_without_making_it_current(tmp_path):
    data = backend(tmp_path)
    old = memory('old', metadata={'epistemic_status': 'SUPERSEDED',
                                 'context': {'scope': {'project': 'atelier'}}})
    data.store(old)
    assert not recall(data, '2026-11-02T12:00:00Z').items
    historical = recall(data, '2026-11-02T12:00:00Z', mode='historical').items[0]
    assert historical.epistemic_status == 'SUPERSEDED' and historical.needs_review
    assert historical.provenance == old.provenance


def test_payload_budget_omits_complete_evidence_instead_of_stripping_dates(tmp_path):
    data = backend(tmp_path)
    data.store(memory())
    bundle = recall(data, '2026-11-02T12:00:00Z')
    full = render(bundle, max_payload_chars=20000)
    short = render(bundle, max_payload_chars=full.payload_chars - 1)
    assert not json.loads(short.text)['items']
    assert short.omitted_ids == ('dated',)
