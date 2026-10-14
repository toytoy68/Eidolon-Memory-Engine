# ==========================================================
# Projet      : Eidolon Memory Engine
# Organisation: Eidolon Core Technologies (ECT)
# Fichier     : tests/claude_memory_eval/test_passage_probes_g214.py
# Description : Sondes Claude G214-6 sur le découpage canonique en passages (passages.py, fichier GPT non modifié)
# Standard    : Eidolon Presentation Standard v1
# ==========================================================
"""Independent probes of core/indexing/passages.py (b37a72c). Positive tests pin what holds; strict xfail
documents a finding. Frozen corpora are not touched."""
import random
from dataclasses import replace

import pytest

from hashlib import sha256

from core.indexing.passages import split_passages, verify_passage

_RNG = random.Random(214)
TEXT = "".join(_RNG.choice("abcdéèàç XYZ\n🙂") for _ in range(5000))


def test_passages_cover_the_whole_text_deterministically_and_verify():
    passages = split_passages("doc", 3, TEXT, size=512, overlap=64)
    assert passages == split_passages("doc", 3, TEXT, size=512, overlap=64)
    assert passages[0].start == 0 and passages[-1].end == len(TEXT)
    assert all(b.start < a.end for a, b in zip(passages, passages[1:]))          # no gap
    assert all(verify_passage(p, TEXT, document_id="doc", revision=3) for p in passages)
    assert len({p.passage_id for p in passages}) == len(passages)


def test_identity_changes_with_revision_and_configuration():
    a = split_passages("doc", 1, TEXT)[0].passage_id
    assert a != split_passages("doc", 2, TEXT)[0].passage_id
    assert a != split_passages("doc", 1, TEXT, size=1000)[0].passage_id
    assert a != split_passages("other", 1, TEXT)[0].passage_id


def test_any_change_of_the_canonical_text_under_a_passage_fails_verification():
    passage = split_passages("doc", 1, TEXT, size=512, overlap=64)[2]
    edited = TEXT[:passage.start + 10] + "Z" + TEXT[passage.start + 11:]
    if edited != TEXT:
        assert not verify_passage(passage, edited, document_id="doc", revision=1)
    assert not verify_passage(passage, TEXT[:passage.end - 1], document_id="doc", revision=1)  # truncated canon
    assert not verify_passage(replace(passage, start=passage.start + 1, end=passage.end + 1), TEXT,
                            document_id="doc", revision=1)


def test_empty_text_has_no_passage():
    assert split_passages("doc", 1, "") == ()


def test_a_passage_from_another_revision_or_document_is_not_verified_for_this_one():
    """P1 (G214), fixed in c8fdc21: passage_id is recomputed from the claimed metadata."""
    passage = split_passages("doc", 1, TEXT)[0]
    for claimed in (replace(passage, revision=7), replace(passage, document_id="secret-profile-doc")):
        assert not verify_passage(claimed, TEXT, document_id=claimed.document_id, revision=claimed.revision)
    assert not verify_passage(replace(passage, passage_id="0" * 64), TEXT, document_id="doc", revision=1)


def test_undecodable_text_is_a_value_error():
    """A lone surrogate raises UnicodeEncodeError, a ValueError subclass: callers catching ValueError hold."""
    with pytest.raises(ValueError):
        split_passages("doc", 1, "a\udc80b")


def forge(passage, document_id, revision):
    """A self-consistent passage claiming another owner: the identity is a plain hash, anyone can recompute it."""
    identity = sha256(f"passage-v1:{document_id}:{revision}:{passage.size}:{passage.overlap}:{passage.start}:"
                      f"{passage.end}:{passage.text_sha256}".encode()).hexdigest()
    return replace(passage, document_id=document_id, revision=revision, passage_id=identity)


def test_trusted_document_and_revision_reject_a_recomputed_forgery():
    passage = split_passages("public-doc", 1, TEXT)[0]
    forged = forge(passage, "private-doc", 9)
    assert not verify_passage(forged, TEXT, document_id="public-doc", revision=1)
    assert not verify_passage(passage, TEXT, document_id="public-doc", revision=2)
    assert verify_passage(passage, TEXT, document_id="public-doc", revision=1)


def test_ownership_cannot_be_skipped_by_omitting_trusted_metadata():
    """P3 (G214), fixed in 70a241e: document_id and revision are mandatory keyword arguments."""
    passage = split_passages("public-doc", 1, TEXT)[0]
    for kwargs in ({}, {"document_id": "public-doc"}, {"revision": 1}):
        with pytest.raises(TypeError):
            verify_passage(forge(passage, "private-doc", 9), TEXT, **kwargs)
    with pytest.raises(TypeError):
        verify_passage(passage, TEXT, "public-doc", 1)                         # keyword-only, never positional
