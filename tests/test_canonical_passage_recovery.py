# ==========================================================
# Projet      : Eidolon Memory Engine
# Organisation: Eidolon Core Technologies (ECT)
# Fichier     : tests/test_canonical_passage_recovery.py
# Description : Régressions G186, exclusion des références et frontières de contexte Unicode
# Standard    : Eidolon Presentation Standard v1
# ==========================================================
import unicodedata

import pytest

from core.indexing.port import IndexHit
from core.retrieval.archive_chunks import chunk_messages, resolve_passage
from core.retrieval.contextual import ContextualRecall
from tests.test_archive_chunks import archive, store_archive
from tests.test_contextual_recall import backend, store
from tests.test_indexed_recall import Candidates


def hit(reference=None):
    ranking = {'revision': 1}
    if reference is not None:
        ranking['passage'] = reference
    return IndexHit('archive', 1.0, ranking)


@pytest.mark.parametrize('invalid', [None,
    {'message_index': 6, 'start': 0, 'end': 3},
    {'message_index': 0, 'start': 0, 'end': 999}])
def test_rejected_archive_candidate_does_not_hide_later_valid_passage(tmp_path, invalid):
    data = backend(tmp_path)
    text = 'Ne pas acheter la V100 maintenant.'
    store_archive(data, [text])
    valid = {'message_index': 0, 'start': 7, 'end': len(text)}
    result = ContextualRecall(data, index=Candidates([hit(invalid), hit(valid)])).recall('carte graphique')
    assert [item.content for item in result.items] == [text]
    reason = 'INDEX_PASSAGE_MISSING' if invalid is None else 'INDEX_PASSAGE_UNRESOLVED'
    assert result.excluded_counts == {reason: 1}


def test_invalid_archive_candidate_does_not_abort_other_information(tmp_path):
    data = backend(tmp_path)
    store_archive(data, ['Un message.'])
    store(data, 'valid', content='Evidence from another information item.')
    candidates = Candidates([hit({'message_index': 99, 'start': 0, 'end': 4}),
                             IndexHit('valid', 0.5, {'revision': 1})])
    result = ContextualRecall(data, index=candidates).recall('query', max_items=1)
    assert [item.information_id for item in result.items] == ['valid']
    assert result.excluded_counts == {'INDEX_PASSAGE_UNRESOLVED': 1}


def test_missing_passage_is_explicit_even_with_lexical_overlap(tmp_path):
    data = backend(tmp_path)
    store_archive(data, ['Acheter la V100.'])
    result = ContextualRecall(data, index=Candidates([hit()])).recall('V100')
    assert not result.items
    assert result.excluded_counts == {'INDEX_PASSAGE_MISSING': 1}


def test_nonarchive_with_passage_is_excluded(tmp_path):
    data = backend(tmp_path)
    store(data, 'archive', content='Plain information.')
    result = ContextualRecall(data, index=Candidates([
        hit({'message_index': 0, 'start': 0, 'end': 3})])).recall('query')
    assert not result.items
    assert result.excluded_counts == {'INDEX_PASSAGE_UNRESOLVED': 1}


def test_small_budget_keeps_omitted_negation_explicit():
    text = 'Ne pas acheter le GPU cette semaine.'
    start = text.index('GPU')
    excerpt, reference = resolve_passage(archive([text]),
        {'message_index': 0, 'start': start, 'end': len(text)}, 10)
    assert len(excerpt) <= 10
    assert excerpt == text[reference['start']:reference['end']]
    assert reference['left_context'] == 'partial'
    assert reference['left_markers_dropped'] == 2


def test_context_extension_stays_in_the_same_sentence():
    text = 'Avant : acheter. Ne jamais acheter cette carte.'
    sentence = text.index('Ne jamais')
    start = text.index('cette')
    excerpt, reference = resolve_passage(archive([text]),
        {'message_index': 0, 'start': start, 'end': len(text)}, 100)
    assert excerpt == text[sentence:]
    assert reference['left_context'] == 'sentence'
    assert reference['left_markers_dropped'] == 0


@pytest.mark.parametrize('mark', ['\u0301', '\u093e', '\u20dd'])
@pytest.mark.parametrize('overlap', [0, 8, 32])
def test_chunks_preserve_coverage_and_combining_boundaries(mark, overlap):
    text = ('a' + mark) * 100 + ' ' + ('e' + mark) * 100
    chunks = chunk_messages(archive([text]), max_chars=33, overlap=overlap)
    covered = set()
    for chunk in chunks:
        ref = chunk.reference
        assert 0 < len(chunk.text) <= 33
        assert chunk.text == text[ref['start']:ref['end']]
        assert not unicodedata.category(chunk.text[0]).startswith('M')
        if ref['end'] < len(text):
            assert not unicodedata.category(text[ref['end']]).startswith('M')
        covered.update(range(ref['start'], ref['end']))
    assert covered == set(range(len(text)))


def test_oversized_combining_sequence_is_refused_not_split_or_silently_dropped():
    with pytest.raises(ValueError, match='combining sequence'):
        chunk_messages(archive(['a' + '\u0301' * 40]), max_chars=32, overlap=8)
