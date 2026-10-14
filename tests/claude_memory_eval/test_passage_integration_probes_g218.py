# ==========================================================
# Projet      : Eidolon Memory Engine
# Organisation: Eidolon Core Technologies (ECT)
# Fichier     : tests/claude_memory_eval/test_passage_integration_probes_g218.py
# Description : Sondes Claude G218-4 : coût et identité des passages avant leur entrée dans Qdrant
# Standard    : Eidolon Presentation Standard v1
# ==========================================================
"""Characterisation probes for a passage-level Qdrant index (study: Core docs/proposals/
2026-10-13-passages-qdrant-calibration.md). They pin today's behaviour of passages.py so the integration
design accounts for it. Nothing is written to Qdrant."""
import random

from core.indexing.passages import split_passages, verify_passage

_RNG = random.Random(218)
TEXT = "".join(_RNG.choice("abcdefgh éàç\n") for _ in range(6000))


def ids(text, revision=1):
    return [p.passage_id for p in split_passages("doc", revision, text)]


def test_an_edit_at_the_start_changes_every_passage_identity():
    """Fixed character windows: one inserted character shifts every window. Integration cost: an edit
    re-embeds the whole document, so the worker must budget per document, not per passage."""
    before, after = ids(TEXT), ids("X" + TEXT)
    assert not set(before) & set(after)


def test_an_edit_at_the_end_keeps_the_earlier_passages_only_within_the_same_revision():
    """Even unchanged windows get new identities with a new revision: stale points of revision N are never
    overwritten by revision N+1, so they must be filtered at read time or retired with their generation."""
    before = split_passages("doc", 1, TEXT)
    same_revision = split_passages("doc", 1, TEXT[:-10] + "0123456789")
    next_revision = split_passages("doc", 2, TEXT[:-10] + "0123456789")
    assert [p.passage_id for p in before[:-1]] == [p.passage_id for p in same_revision[:-1]]
    assert not {p.passage_id for p in before} & {p.passage_id for p in next_revision}


def test_a_stale_passage_is_rejected_once_the_canon_moves_to_a_new_revision():
    """Read-time defence for stale points: the trusted canonical revision rejects revision-1 passages."""
    old = split_passages("doc", 1, TEXT)[0]
    assert verify_passage(old, TEXT, document_id="doc", revision=1)
    assert not verify_passage(old, TEXT, document_id="doc", revision=2)       # same text, canon now at rev 2


def test_passage_count_grows_linearly_and_stays_bounded_by_size():
    for length in (0, 1, 1200, 1201, 10_000):
        passages = split_passages("doc", 1, "a" * length)
        assert all(p.end - p.start <= 1200 for p in passages)
        if length == 0:
            assert passages == ()
        else:
            assert len(passages) <= -(-length // (1200 - 160))
