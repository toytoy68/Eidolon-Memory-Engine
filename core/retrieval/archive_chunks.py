# ==========================================================
# Projet      : Eidolon Memory Engine
# Organisation: Eidolon Core Technologies (ECT)
# Fichier     : core/retrieval/archive_chunks.py
# Description : Bounded verbatim archive chunks with canonical message offsets.
# Standard    : Eidolon Presentation Standard v1
# ==========================================================
"""Never combine messages or infer truth, corrections or authorization."""
from dataclasses import dataclass
import json
import re
import unicodedata

from core.retrieval.chatgpt_passages import _sentence_start, _WORD, _MARKERS

CHUNK_POLICY = 'chatgpt-archive-chunks-v2'
PASSAGE_POLICY = 'chatgpt-indexed-passage-v2'


@dataclass(frozen=True)
class ArchiveChunk:
    text: str
    reference: dict


def _archive(content):
    try:
        value = json.loads(content)
    except (ValueError, TypeError) as exc:
        raise ValueError('invalid conversation archive') from exc
    if not isinstance(value, dict) or not isinstance(value.get('messages'), list):
        raise ValueError('invalid conversation archive')
    return value


def _before_combining(text, boundary, floor):
    """Keep a base character and its following Unicode marks in the same chunk.

    This preserves original offsets, not a full Unicode grapheme segmentation.
    Emoji ZWJ sequences and regional-indicator pairs are outside this policy.
    """
    while boundary > floor and boundary < len(text) and unicodedata.category(text[boundary]).startswith('M'):
        boundary -= 1
    return boundary


def chunk_messages(content, *, max_chars=1200, overlap=160, max_chunks=10000):
    if (type(max_chars) is not int or not 32 <= max_chars <= 16000
            or type(overlap) is not int or not 0 <= overlap < max_chars
            or type(max_chunks) is not int or not 1 <= max_chunks <= 100000):
        raise ValueError('invalid chunk limits')
    chunks = []
    for i, message in enumerate(_archive(content)['messages']):
        if (not isinstance(message, dict) or message.get('role') not in {'user', 'assistant'}
                or not isinstance(message.get('content'), str)):
            continue
        text = message['content']
        start = 0
        while start < len(text):
            if len(chunks) == max_chunks:
                raise ValueError('archive chunk limit exceeded')
            end = min(start + max_chars, len(text))
            if end < len(text):
                boundaries = list(re.finditer(r'\s+', text[start:end]))
                if boundaries and boundaries[-1].end() >= max_chars // 2:
                    end = start + boundaries[-1].end()
            end = _before_combining(text, end, start)
            if end == start:
                raise ValueError('combining sequence exceeds chunk character limit')
            chunks.append(ArchiveChunk(text[start:end],
                {'message_index': i, 'start': start, 'end': end}))
            if end == len(text):
                break
            next_start = max(start + 1, end - overlap)
            if next_start < end:
                boundary = re.search(r'\s+', text[next_start:end])
                next_start = next_start + boundary.end() if boundary else end
            next_start = _before_combining(text, next_start, start)
            if next_start <= start:
                next_start = end
            start = next_start
    return tuple(chunks)


def validate_reference(reference):
    if (not isinstance(reference, dict)
            or set(reference) != {'message_index', 'start', 'end'}
            or any(type(reference[k]) is not int for k in reference)
            or reference['message_index'] < 0 or reference['start'] < 0
            or reference['end'] <= reference['start']):
        raise ValueError('invalid index passage reference')


def _canonical_message(content, reference):
    validate_reference(reference)
    archive = _archive(content)
    i, start, stop = (reference[k] for k in ('message_index', 'start', 'end'))
    if i >= len(archive['messages']):
        raise ValueError('index passage message is absent')
    message = archive['messages'][i]
    if (not isinstance(message, dict) or message.get('role') not in {'user', 'assistant'}
            or not isinstance(message.get('content'), str)
            or stop > len(message['content'])):
        raise ValueError('index passage does not match a canonical message')
    return archive, message


def validate_canonical_reference(content, reference):
    """Validate shape, role and offsets against canonical content, without selecting an excerpt."""
    _canonical_message(content, reference)


def resolve_passage(content, reference, max_chars):
    """Resolve canonical offsets, extending left when the selected passage and context fit."""
    if type(max_chars) is not int or max_chars < 1:
        raise ValueError('invalid passage budget')
    archive, message = _canonical_message(content, reference)
    i, start, stop = (reference[k] for k in ('message_index', 'start', 'end'))
    text = message['content']
    end = min(stop, start + max_chars)
    sentence = _sentence_start(text, start)
    if end - sentence <= max_chars:
        start = sentence
    dropped = sum(1 for word in _WORD.finditer(text, sentence, start)
                  if unicodedata.normalize('NFC', word.group().casefold()) in _MARKERS)
    ref = dict(conversation_id=archive.get('conversation_id'), message_index=i,
        node_id=message.get('node_id'), message_id=message.get('message_id'),
        parent=message.get('parent'), role=message['role'], created_at=message.get('created_at'),
        start=start, end=end, policy=PASSAGE_POLICY,
        left_context=('message_start' if start == 0 else 'sentence' if start == sentence else 'partial'),
        left_markers_dropped=dropped,
        right_context='message_end' if end == len(text) else 'partial')
    return text[start:end], ref
