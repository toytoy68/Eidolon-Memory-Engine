# ==========================================================
# Projet      : Eidolon Memory Engine
# Organisation: Eidolon Core Technologies (ECT)
# Fichier     : tests/claude_memory_eval/test_canonical_probes.py
# Description : Contre-revue Claude G181/G182 : sondes indépendantes du rappel canonique par index et des passages
# Standard    : Eidolon Presentation Standard v1
# ==========================================================
"""Independent probes (Claude, G183 order item 1). Positive tests pin behaviour that holds; xfail(strict)
tests document a finding and turn red the day it is resolved, so the resolution is noticed."""
import json
import random
import unicodedata

import pytest

from core.indexing.port import IndexHit
from core.retrieval.archive_chunks import chunk_messages, resolve_passage
from core.retrieval.chatgpt_passages import _MARKERS, _WORD, _sentence_start, select_passage
from core.retrieval.contextual import ContextualRecall
from tests.test_archive_chunks import archive, store_archive
from tests.test_contextual_recall import backend
from tests.test_indexed_recall import Candidates


def passage_hit(reference, revision=1):
    return IndexHit('archive', 1.0, {'revision': revision, 'policy': 'synthetic', 'passage': reference})


# --- A5-02 v3 (G180 fix): randomised left-window boundary -------------------------------------------------
VOCAB = ['ne', 'pas', 'jamais', 'acheter', 'V100', 'maintenant', 'sauf', 'si', "n'achète", "don't",
         'abcdefghijklmnopqrstuvwxyz', 'é', 'été', "l'été", 'GPU', 'rien', 'x', '1234']
SEPS = [' ', ' ', ', ', '. ', '! ', '\n', ' … ', '? ', '  ', '\n  ', '»  ']


def _n(text):
    return unicodedata.normalize('NFC', text).casefold()


@pytest.mark.parametrize('seed', range(4))
def test_left_window_never_starts_inside_a_word_and_counts_dropped_markers(seed):
    rng = random.Random(seed)
    for _ in range(3000):
        text = ''.join(rng.choice(VOCAB) + rng.choice(SEPS) for _ in range(rng.randint(1, 25))).rstrip()
        query = rng.choice(['V100', 'GPU acheter', 'maintenant', 'été', '1234 x'])
        budget = rng.randint(4, 80)
        found = select_passage(json.dumps({'messages': [{'role': 'user', 'content': text}]}), query, budget)
        if found is None:
            continue
        passage, ref = found
        start, sentence = ref['start'], _sentence_start(text, ref['start'])
        assert text[start:ref['end']] == passage
        words = list(_WORD.finditer(text, sentence))
        assert not any(w.start() < start < w.end() for w in words), (text, query, budget)
        assert any(_n(t) in _n(passage[:budget]) for t in query.split()), (text, query, budget)
        if ref['left_context'] in ('partial', 'none'):          # window starts after the sentence start
            dropped = sum(1 for w in _WORD.finditer(text, sentence, start) if _n(w.group()) in _MARKERS)
            assert ref['left_markers_dropped'] == dropped
        else:
            assert ref['left_markers_dropped'] == 0


# --- G181/G182: canonical resolution of index passages ----------------------------------------------------
def test_index_passage_is_read_from_the_current_canonical_text(tmp_path):
    data = backend(tmp_path)
    store_archive(data, ['Ne pas acheter la V100 maintenant.', 'Autre message.'])
    item = ContextualRecall(data, index=Candidates([passage_hit({'message_index': 0, 'start': 7, 'end': 34})])
                            ).recall('carte graphique').items[0]
    assert item.content == 'acheter la V100 maintenant.'
    ref = item.excerpt_reference
    assert (ref['left_context'], ref['left_markers_dropped']) == ('partial', 2)   # « Ne pas » signalled
    assert ref['policy'] == 'chatgpt-indexed-passage-v1'


def test_stale_index_revision_never_resolves_offsets_against_new_text(tmp_path):
    from dataclasses import replace
    data = backend(tmp_path)
    old = store_archive(data, ['Acheter la V100 maintenant.'])
    data.update('archive', replace(old, content=archive(['Ne jamais acheter la V100.'])), previous_revision=1)
    result = ContextualRecall(data, index=Candidates([passage_hit({'message_index': 0, 'start': 0, 'end': 27})])
                              ).recall('V100')
    assert result.items == () or list(result.items) == []
    assert result.excluded_counts == {'INDEX_REVISION_MISMATCH': 1}


@pytest.mark.xfail(strict=True, reason='Claude finding P1: one out-of-range passage aborts the whole recall '
                   'instead of being excluded and counted like a revision mismatch')
def test_one_unresolvable_passage_is_excluded_not_fatal(tmp_path):
    data = backend(tmp_path)
    store_archive(data, ['Un seul message.'])
    result = ContextualRecall(data, index=Candidates([passage_hit({'message_index': 5, 'start': 0, 'end': 3})])
                              ).recall('message')
    assert result.excluded_counts.get('INDEX_PASSAGE_UNRESOLVED') == 1


@pytest.mark.xfail(strict=True, reason='Claude finding P2: a semantic hit on an archive WITHOUT a passage '
                   'reference falls back to lexical selection and is dropped silently, with no exclusion count')
def test_archive_hit_without_lexical_overlap_is_not_dropped_silently(tmp_path):
    data = backend(tmp_path)
    store_archive(data, ['Ne pas acheter la V100 maintenant.'])
    hit = IndexHit('archive', 1.0, {'revision': 1, 'policy': 'synthetic'})
    result = ContextualRecall(data, index=Candidates([hit])).recall('carte graphique')
    assert result.items or result.excluded_counts


@pytest.mark.xfail(strict=True, reason='Claude finding P3: the indexed path does not extend to the sentence '
                   'start like select_passage v3; a negation just before the chunk is only counted')
def test_indexed_passage_keeps_the_sentence_start_when_budget_allows(tmp_path):
    data = backend(tmp_path)
    store_archive(data, ['Ne pas acheter la V100 maintenant.'])
    item = ContextualRecall(data, index=Candidates([passage_hit({'message_index': 0, 'start': 7, 'end': 34})])
                            ).recall('carte graphique', max_item_chars=200).items[0]
    assert item.content.startswith('Ne pas')


@pytest.mark.xfail(strict=True, reason='Claude finding P4: an unbroken run is cut at max_chars, so a chunk can '
                   'start between a letter and its combining accent')
def test_chunks_never_start_on_a_combining_mark():
    text = ('é' * 40 + ' ') * 4
    for chunk in chunk_messages(archive([text]), max_chars=33, overlap=8):
        assert unicodedata.category(chunk.text[0]) != 'Mn', chunk.reference
