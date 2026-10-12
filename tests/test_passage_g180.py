# ==========================================================
# Projet      : Eidolon Memory Engine
# Organisation: Eidolon Core Technologies (ECT)
# Fichier     : tests/test_passage_g180.py
# Description : Integration regressions for left-context word boundaries.
# Standard    : Eidolon Presentation Standard v1
# ==========================================================
import json
import pytest
from core.retrieval.chatgpt_passages import select_passage

@pytest.mark.parametrize('budget', [18, 24])
def test_left_context_does_not_start_inside_word(budget):
    text = 'Ne pas abcdefghijklmnopqrstuvwxyz acheter V100 maintenant.'
    archive = json.dumps({'messages': [{'role': 'user', 'content': text}]})
    passage, ref = select_passage(archive, 'V100', budget)
    start = ref['start']
    assert not (start and text[start - 1].isalnum() and text[start].isalnum())
    assert 'V100' in passage[:budget]
    assert ref['left_markers_dropped'] == 2
    assert text[ref['start']:ref['end']] == passage
