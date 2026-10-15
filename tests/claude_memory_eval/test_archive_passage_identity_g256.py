# ==========================================================
# Projet      : Eidolon Memory Engine
# Organisation: Eidolon Core Technologies (ECT)
# Fichier     : tests/claude_memory_eval/test_archive_passage_identity_g256.py
# Description : Identité des points de passage : séparateurs, types, bornes, Unicode (Claude, G256-4)
# Standard    : Eidolon Presentation Standard v1
# ==========================================================
"""Synthetic only. A passage point identity must be injective over valid inputs, refuse inputs no canonical
archive can produce, and never carry text."""
import itertools
import unicodedata

import pytest

from core.retrieval.archive_chunks import chunk_messages
from tests.claude_memory_eval.archive_passage_projection import ArchivePassageProjection, point_id
from tests.test_archive_chunks import archive, store_archive
from tests.test_contextual_recall import backend

D, E = "a" * 64, "b" * 64
REF = {"message_index": 1, "start": 0, "end": 10}


def test_no_value_can_absorb_a_neighbouring_separator():
    # G252 joined fields with ':' — these pairs named the SAME point.
    for left, right in [(("a", "1:b", D), ("a:1", "b", D)), (("a", 1, "2:" + D), ("a:1", 2, D))]:
        with pytest.raises(ValueError):
            point_id(*left, REF)
        with pytest.raises(ValueError):
            point_id(*right, REF)


@pytest.mark.parametrize("args", [
    ("a", True, D, REF), ("a", 1.0, D, REF), ("a", 0, D, REF), ("a", 1, D.upper(), REF), ("a", 1, D[:-1], REF),
    ("é", 1, D, REF), ("a/b", 1, D, REF), ("", 1, D, REF), (None, 1, D, REF),
    ("a", 1, D, dict(REF, extra=1)), ("a", 1, D, dict(REF, start=10)), ("a", 1, D, dict(REF, start=-1)),
    ("a", 1, D, dict(REF, end=10.0)), ("a", 1, D, dict(REF, message_index=True)), ("a", 1, D, [1, 0, 10]),
])
def test_inputs_no_canonical_archive_can_produce_are_refused(args):
    with pytest.raises(ValueError):
        point_id(*args)


def test_every_component_discriminates_and_the_identity_is_stable():
    values = dict(information_id=("a", "a.b", "a-b", "A"), revision=(1, 2, 10), digest=(D, E),
                  message_index=(0, 1), start=(0, 1), end=(11, 12))
    seen = {}
    for combo in itertools.product(*values.values()):
        info, rev, dig, i, s, e = combo
        pid = point_id(info, rev, dig, {"message_index": i, "start": s, "end": e})
        assert pid not in seen, (combo, seen.get(pid))
        seen[pid] = combo
        assert pid == point_id(info, rev, dig, {"end": e, "start": s, "message_index": i})  # key order free


def test_unicode_offsets_are_code_points_and_normalisation_never_merges(tmp_path):
    nfc = "Crêpe déjà prête. " * 80
    nfd = unicodedata.normalize("NFD", nfc)
    assert nfc != nfd
    ids = []
    for n, text in enumerate((nfc, nfd)):
        data = backend(tmp_path / str(n))
        store_archive(data, ["question", text])
        index = ArchivePassageProjection(data.persistent_root, score=lambda t, p: 1.0)
        ids.append(set(index.project("archive")))
        for point in index.points.values():
            assert set(point) == {"kind", "information_id", "revision", "canonical_sha256", "projection_id",
                                  "passage", "_vector_text"}  # offsets and proofs, never text
            ref = point["passage"]
            message = text if ref["message_index"] == 1 else "question"
            assert 0 <= ref["start"] < ref["end"] <= len(message)
            assert not unicodedata.category(message[ref["start"]]).startswith("M")  # never starts on a mark
    assert not ids[0] & ids[1]  # different bytes, different digest, disjoint identities


def test_whitespace_only_and_empty_messages_produce_no_point(tmp_path):
    assert chunk_messages(archive(["", "   "]))  # the chunker itself keeps whitespace passages
    data = backend(tmp_path)
    store_archive(data, ["", "   \n\t", "réel"])
    index = ArchivePassageProjection(data.persistent_root, score=lambda t, p: 1.0)
    assert [p["passage"]["message_index"] for p in map(index.points.get, index.project("archive"))] == [2]
