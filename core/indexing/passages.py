# ==========================================================
# Projet      : Eidolon Memory Engine
# Organisation: Eidolon Core Technologies (ECT)
# Fichier     : core/indexing/passages.py
# Description : Pure deterministic passage splitting for candidate indexing.
# Standard    : Eidolon Presentation Standard v1
# ==========================================================
"""Deterministic text passages. No Qdrant writes and no canonical mutation."""
from dataclasses import dataclass
from hashlib import sha256
import re

@dataclass(frozen=True)
class Passage:
    document_id: str
    revision: int
    start: int
    end: int
    text_sha256: str
    passage_id: str
    text: str
    size: int = 1200
    overlap: int = 160

def split_passages(document_id: str, revision: int, text: str, *, size: int = 1200, overlap: int = 160):
    if not isinstance(document_id, str) or re.fullmatch(r"[A-Za-z0-9._-]{1,256}", document_id) is None:
        raise ValueError("invalid document identity")
    if type(revision) is not int or revision < 1 or type(text) is not str:
        raise ValueError("invalid revision or text")
    if type(size) is not int or type(overlap) is not int or not 128 <= size <= 8192 or not 0 <= overlap < size:
        raise ValueError("invalid passage configuration")
    out = []
    step = size - overlap
    for start in range(0, len(text), step):
        end = min(start + size, len(text))
        chunk = text[start:end]
        digest = sha256(chunk.encode("utf-8")).hexdigest()
        identity = sha256(f"passage-v1:{document_id}:{revision}:{size}:{overlap}:{start}:{end}:{digest}".encode()).hexdigest()
        out.append(Passage(document_id, revision, start, end, digest, identity, chunk, size, overlap))
        if end == len(text):
            break
    return tuple(out)

def verify_passage(passage: Passage, canonical_text: str, *,
                   document_id: str, revision: int):
    """Validate content and the self-consistency of the passage identity.

    The caller MUST supply trusted canonical document_id and revision.
    This is not proof of authorization; access rights must be checked separately.
    """
    if (not isinstance(passage, Passage) or type(canonical_text) is not str
            or type(document_id) is not str or type(revision) is not int or revision < 1):
        return False
    if passage.document_id != document_id:
        return False
    if passage.revision != revision:
        return False
    if (type(passage.revision) is not int or passage.revision < 1
            or type(passage.size) is not int or type(passage.overlap) is not int
            or not 128 <= passage.size <= 8192
            or not 0 <= passage.overlap < passage.size
            or not 0 <= passage.start < passage.end <= len(canonical_text)
            or passage.end - passage.start > passage.size):
        return False
    value = canonical_text[passage.start:passage.end]
    digest = sha256(value.encode("utf-8")).hexdigest()
    expected = sha256(
        f"passage-v1:{passage.document_id}:{passage.revision}:{passage.size}:{passage.overlap}:{passage.start}:{passage.end}:{digest}".encode()
    ).hexdigest()
    return (value == passage.text and digest == passage.text_sha256
            and passage.passage_id == expected)
