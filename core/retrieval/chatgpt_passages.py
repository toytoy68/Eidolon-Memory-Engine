# ==========================================================
# Projet      : Eidolon Memory Engine
# Organisation: Eidolon Core Technologies (ECT)
# Fichier     : core/retrieval/chatgpt_passages.py
# Description : Select a bounded verbatim message passage with its left context; never join conversation branches.
# Standard    : Eidolon Presentation Standard v1
# ==========================================================

"""Select a bounded verbatim message passage; never join conversation branches."""
from collections import Counter
import json
import re
import unicodedata
from core.retrieval.ranking import terms


# Combining marks continue a word, without changing offsets in original text.
_COMBINING = ''.join(f'{chr(a)}-{chr(b)}' for a, b in (
    (0x0300, 0x036f), (0x1ab0, 0x1aff), (0x1dc0, 0x1dff), (0x20d0, 0x20ff), (0xfe20, 0xfe2f)))
_WORD = re.compile(r'\w+(?:[' + _COMBINING + r']+\w*)*')
# A5-02 (policy v3): a sentence starts after . ! ? … or a line break followed by spaces, or at the text start.
_SENTENCE_END = re.compile(r'[.!?…]+["»”’)\]]*\s+|\n\s*')
# Words that change the meaning of what follows (negation, exception, condition). Only COUNTED when they
# fall outside the excerpt: a signal for the consumer, never a rewrite or an interpretation.
_MARKERS = frozenset({'ne', 'n', 'pas', 'jamais', 'ni', 'sans', 'non', 'aucun', 'aucune', 'rien', 'sauf',
                      'si', 'not', 'no', 'never', 'nor', 'without', 'unless', 'if', 't'})


def _sentence_start(text, position):
    start = 0
    for boundary in _SENTENCE_END.finditer(text, 0, position):
        if boundary.end() <= position:
            start = boundary.end()
    return start


def _left_context(text, first, last_end, max_chars):
    """(start, kind, dropped markers): the sentence start when the budget allows, else as much left
    context as fits, starting on a word boundary; matched terms always stay fully inside the budget."""
    sentence = _sentence_start(text, first)
    if last_end - sentence <= max_chars:
        return sentence, ('sentence' if sentence < first else 'match'), 0
    start = max(sentence, last_end - max_chars)
    words = [m.start() for m in _WORD.finditer(text, sentence, first + 1) if m.start() >= start]
    if start not in words:
        start = words[0] if words else first
    dropped = sum(1 for m in _WORD.finditer(text, sentence, start)
                  if unicodedata.normalize('NFC', m.group().casefold()) in _MARKERS)
    return start, ('partial' if start < first else 'none'), dropped


def select_passage(content, query, max_chars):
    try:
        archive=json.loads(content)
        if not isinstance(archive,dict) or not isinstance(archive.get('messages'),list):
            return None
        wanted=set(terms(query));best=None
        for index,message in enumerate(archive['messages']):
            if not isinstance(message,dict) or message.get('role') not in {'user','assistant'}:
                continue
            text=message.get('content')
            if not isinstance(text,str):
                continue
            matched=[]
            for match in _WORD.finditer(text):
                word=unicodedata.normalize('NFC',match.group().casefold())
                if word in wanted:
                    matched.append((word,match.start(),match.end()))
            counts=Counter();right=0
            for left,(_,start,_) in enumerate(matched):
                while right<len(matched) and matched[right][2]<=start+max_chars:
                    counts[matched[right][0]]+=1
                    right+=1
                if right>left:
                    # Prefer coverage inside the actual window, then a compact span.
                    score=(len(counts),-(matched[right-1][2]-start))
                    if best is None or score>best[0]:
                        begin,kind,dropped=_left_context(text,start,matched[right-1][2],max_chars)
                        reference=dict(conversation_id=archive.get('conversation_id'),
                            node_id=message.get('node_id'),message_id=message.get('message_id'),
                            parent=message.get('parent'),role=message['role'],created_at=message.get('created_at'),
                            start=begin,end=len(text),policy='chatgpt-message-passage-v3',
                            left_context=kind,left_markers_dropped=dropped)
                        best=(score,text[begin:],reference)
                if right>left:
                    word=matched[left][0]
                    counts[word]-=1
                    if not counts[word]:
                        del counts[word]
                else:
                    right=left+1
        return (best[1],best[2]) if best else None
    except (ValueError,TypeError):
        return None
