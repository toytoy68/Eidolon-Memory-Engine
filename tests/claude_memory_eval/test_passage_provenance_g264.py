# ==========================================================
# Projet      : Eidolon Memory Engine
# Organisation: Eidolon Core Technologies (ECT)
# Fichier     : tests/claude_memory_eval/test_passage_provenance_g264.py
# Description : Provenance des passages : chaque extrait cité est la tranche exacte du canon vérifié (Claude, G264-7)
# Standard    : Eidolon Presentation Standard v1
# ==========================================================
"""Synthetic archives; experimental projection only (no production wiring). For every passage the
projection can produce, force its selection and check, against bytes read INDEPENDENTLY:

  cited content == canonical message text[start:end]   and   reported digest == sha256(canonical bytes)
"""
from hashlib import sha256
import json
import unicodedata

import pytest

import core.retrieval.archive_chunks as archive_chunks
from core.indexing.worker_canonical import CanonicalReader
from core.retrieval.contextual import ContextualRecall
from tests.claude_memory_eval.archive_passage_projection import ArchivePassageProjection
from tests.test_archive_chunks import store_archive
from tests.test_contextual_recall import backend

LONG = " ".join(f"Phrase numéro {n:03d} sur la sauvegarde." for n in range(120))   # several passages
MESSAGES = [
    "Ligne une.\r\nLigne deux avec CRLF.\r\n\r\nTroisième paragraphe.",
    unicodedata.normalize("NFD", "Crêpe déjà prête, café noir.") + " 👨‍👩‍👧 famille.",
    "Même paragraphe répété.\n\nMême paragraphe répété.",
    "Même paragraphe répété.\n\nMême paragraphe répété.",            # identical text, other message
    LONG,
]


def canonical(data):
    memory, digest = CanonicalReader(data.persistent_root)("archive")
    raw = (data.persistent_root / "archive.md").read_bytes()
    assert sha256(raw).hexdigest() == digest                          # the reader's digest is of the bytes
    return json.loads(memory.content)["messages"], digest


def cite(data, index, pid):
    pick = lambda text, point, _pid=pid: 1.0 if index.points_by_id.get(_pid) is point else 0.0
    index.score = pick
    items = ContextualRecall(data, index=index).recall("sauvegarde", max_items=1, max_item_chars=4000).items
    assert len(items) == 1
    return items[0]


@pytest.fixture
def corpus(tmp_path):
    data = backend(tmp_path)
    store_archive(data, MESSAGES)
    index = ArchivePassageProjection(data.persistent_root, score=lambda t, p: 0.0)
    ids = index.project("archive")
    index.points_by_id = dict(index.points)
    return data, index, ids


def test_every_projected_passage_cites_the_exact_canonical_slice(corpus):
    data, index, ids = corpus
    messages, digest = canonical(data)
    assert len(ids) > len(MESSAGES)                                   # the long message has several passages
    for pid in ids:
        point = index.points[pid]
        item = cite(data, index, pid)
        ref = item.excerpt_reference
        text = messages[ref["message_index"]]["content"]
        assert item.content == text[ref["start"]:ref["end"]], (pid, ref)
        assert ref["message_index"] == point["passage"]["message_index"]
        assert ref["message_id"] == f"m-{ref['message_index']}"
        # Left extension to a sentence start is allowed, never beyond the indexed passage's end.
        assert ref["start"] <= point["passage"]["start"] and ref["end"] <= point["passage"]["end"]
        assert item.ranking["index"]["canonical_sha256"] == digest


def test_crlf_and_decomposed_unicode_are_cited_byte_for_byte(corpus):
    data, index, ids = corpus
    for n in (0, 1):
        pid = next(p for p in ids if index.points[p]["passage"]["message_index"] == n)
        item = cite(data, index, pid)
        assert item.content == MESSAGES[n]                            # CRLF kept, NFD not recomposed
        assert "\r\n" in item.content if n == 0 else unicodedata.is_normalized("NFD", item.content[:27])


def test_identical_paragraphs_in_two_messages_cite_the_selected_message(corpus):
    data, index, ids = corpus
    for n in (2, 3):
        pid = next(p for p in ids if index.points[p]["passage"]["message_index"] == n)
        item = cite(data, index, pid)
        assert item.excerpt_reference["message_index"] == n and item.excerpt_reference["message_id"] == f"m-{n}"


def test_a_change_after_selection_is_never_mixed_with_the_old_proof(corpus, monkeypatch):
    """The canon is rewritten (same revision, outside any lock) right after the candidate was verified:
    the cited slice and the reported digest must both describe the VERIFIED bytes, never a mix."""
    data, index, ids = corpus
    leaf = data.persistent_root / "archive.md"
    before = leaf.read_bytes()
    messages, digest = canonical(data)
    real = archive_chunks.validate_canonical_reference

    def rewrite_then_validate(content, reference):
        leaf.write_bytes(before.replace("Ligne deux".encode(), "LIGNE XXXX".encode()))
        return real(content, reference)
    monkeypatch.setattr(archive_chunks, "validate_canonical_reference", rewrite_then_validate)
    pid = next(p for p in ids if index.points[p]["passage"]["message_index"] == 0)
    index.score = lambda text, point, _pid=pid: 1.0 if index.points_by_id.get(_pid) is point else 0.0
    result = ContextualRecall(data, index=index).recall("sauvegarde", max_items=1, max_item_chars=4000)
    for item in result.items:                                     # cited: then old bytes AND old proof
        assert "Ligne deux" in item.content and "XXXX" not in item.content
        assert item.ranking["index"]["canonical_sha256"] == digest == sha256(before).hexdigest()
    if not result.items:                                          # or refused: an explicit reason, no mix
        assert sum(result.excluded_counts.values()) >= 1
    monkeypatch.undo()
    # Once the change is visible, the old point is refused (same revision, other bytes).
    result = ContextualRecall(data, index=index).recall("sauvegarde", max_items=1)
    assert result.items == () and result.excluded_counts.get("INDEX_DIGEST_MISMATCH", 0) >= 1


def test_a_change_between_index_query_and_canonical_check_is_refused(corpus):
    data, index, ids = corpus
    leaf = data.persistent_root / "archive.md"
    original = leaf.read_bytes()
    target = next(p for p in ids if index.points[p]["passage"]["message_index"] == 0)

    def score_and_change(text, point):
        if leaf.read_bytes() == original:
            leaf.write_bytes(original.replace("Ligne une".encode(), "LIGNE UNE".encode()))
        return 1.0 if index.points_by_id.get(target) is point else 0.0
    index.score = score_and_change
    result = ContextualRecall(data, index=index).recall("sauvegarde", max_items=1)
    assert result.items == () and result.excluded_counts.get("INDEX_DIGEST_MISMATCH", 0) >= 1
