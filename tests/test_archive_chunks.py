# ==========================================================
# Projet      : Eidolon Memory Engine
# Organisation: Eidolon Core Technologies (ECT)
# Fichier     : tests/test_archive_chunks.py
# Description : Exact message chunks and semantic candidate references.
# Standard    : Eidolon Presentation Standard v1
# ==========================================================
import json
from dataclasses import replace

import pytest

from core.backend.models import Memory
from core.indexing.port import IndexHit
from core.retrieval.contextual import ContextualRecall
from core.retrieval.archive_chunks import chunk_messages, resolve_passage
from tests.test_contextual_recall import backend
from tests.test_indexed_recall import Candidates


def archive(texts):
    return json.dumps({'conversation_id': 'conversation', 'messages': [
        {'content': text, 'node_id': f'n-{i}', 'message_id': f'm-{i}',
         'parent': 'root', 'role': 'user' if i % 2 == 0 else 'assistant',
         'created_at': 1700000000 + i} for i, text in enumerate(texts)]}, ensure_ascii=False)


def store_archive(data, texts):
    m = Memory('archive', content=archive(texts),
        metadata={'archive_kind': 'conversation', 'epistemic_status': 'UNVERIFIED'},
        provenance={'importer': 'chatgpt-archive-v1'})
    data.store(m)
    return m


def test_chunks_cover_text_and_never_mix_messages():
    texts = ['Ne pas acheter maintenant. ' * 45, 'Autre branche : garder la carte.']
    chunks = chunk_messages(archive(texts), max_chars=120, overlap=20)
    assert len(chunks) > 2
    for i, text in enumerate(texts):
        covered = set()
        for chunk in chunks:
            r = chunk.reference
            if r['message_index'] == i:
                assert chunk.text == text[r['start']:r['end']]
                assert 0 < len(chunk.text) <= 120
                covered.update(range(r['start'], r['end']))
        assert covered == set(range(len(text)))
    assert chunks == chunk_messages(archive(texts), max_chars=120, overlap=20)


def test_unicode_and_long_unbroken_word_still_progress():
    text = 'é😀e\u0301' * 150
    chunks = chunk_messages(archive([text]), max_chars=64, overlap=16)
    assert chunks[-1].reference['end'] == len(text)
    assert all(c.text == text[c.reference['start']:c.reference['end']] for c in chunks)


def test_non_dialogue_messages_are_not_indexed():
    content = json.dumps({'messages': [{'role': 'system', 'content': 'secret'},
        {'role': 'tool', 'content': 'tool'}, {'role': 'user', 'content': ['image']},
        {'role': 'assistant', 'content': 'public'}]})
    chunks = chunk_messages(content)
    assert [c.text for c in chunks] == ['public']
    assert chunks[0].reference['message_index'] == 3


@pytest.mark.parametrize('options', [{'max_chars': 0}, {'max_chars': True},
    {'overlap': -1}, {'max_chars': 64, 'overlap': 64}, {'max_chunks': 0}])
def test_invalid_chunk_limits_fail(options):
    with pytest.raises(ValueError):
        chunk_messages(archive(['hello']), **options)


def test_chunk_limit_fails_instead_of_silently_dropping_tail():
    with pytest.raises(ValueError, match='limit'):
        chunk_messages(archive(['word ' * 100]), max_chars=64, overlap=8, max_chunks=2)


@pytest.mark.parametrize('ref', [{'message_index': True, 'start': 0, 'end': 2},
    {'message_index': 0, 'start': -1, 'end': 2},
    {'message_index': 0, 'start': 0, 'end': 999},
    {'message_index': 99, 'start': 0, 'end': 2},
    {'message_index': 0, 'start': 2, 'end': 2},
    {'message_index': 0, 'start': 0, 'end': 2, 'content': 'injected'}])
def test_bad_references_never_become_excerpts(ref):
    with pytest.raises(ValueError):
        resolve_passage(archive(['canonical']), ref, 100)


def test_semantic_candidate_without_shared_words_returns_canonical_message(tmp_path):
    data = backend(tmp_path)
    text = 'Les clichés sont copiés chaque nuit sur le disque externe.'
    store_archive(data, ['Branche précédente.', text])
    ref = chunk_messages(archive(['Branche précédente.', text]))[1].reference
    index = Candidates([IndexHit('archive', 0.8, {'revision': 1, 'passage': ref})])
    result = ContextualRecall(data, index=index).recall('photographies sauvegarde automatique')
    item = result.items[0]
    assert item.content == text and item.needs_review
    assert item.excerpt_reference['message_id'] == 'm-1'
    assert item.excerpt_reference['role'] == 'assistant'
    assert item.excerpt_reference['policy'] == 'chatgpt-indexed-passage-v2'


def test_index_passage_obeys_token_budget_and_offsets(tmp_path):
    data = backend(tmp_path)
    text = 'Ne pas acheter cette carte maintenant.'
    store_archive(data, [text])
    ref = chunk_messages(archive([text]))[0].reference
    index = Candidates([IndexHit('archive', 0.8, {'revision': 1, 'passage': ref})])
    item = ContextualRecall(data, index=index).recall('GPU', max_tokens=6,
        token_counter=len).items[0]
    r = item.excerpt_reference
    assert text[r['start']:r['end']] == item.content == 'Ne pas'
    assert r['right_context'] == 'partial'


def test_changed_revision_is_rejected_before_passage_resolution(tmp_path):
    data = backend(tmp_path)
    m = store_archive(data, ['Old message'])
    data.update('archive', replace(m, content=archive(['New message'])), previous_revision=1)
    index = Candidates([IndexHit('archive', 0.8, {'revision': 1,
        'passage': {'message_index': 0, 'start': 0, 'end': 11}})])
    result = ContextualRecall(data, index=index).recall('query')
    assert not result.items and result.excluded_counts == {'INDEX_REVISION_MISMATCH': 1}


def test_left_context_preserves_negation_when_the_complete_passage_fits():
    text = 'Ne pas acheter le GPU cette semaine.'
    start = text.index('GPU')
    excerpt, ref = resolve_passage(archive([text]),
        {'message_index': 0, 'start': start, 'end': len(text)}, 100)
    assert excerpt == text
    assert ref['left_context'] == 'message_start' and ref['left_markers_dropped'] == 0
