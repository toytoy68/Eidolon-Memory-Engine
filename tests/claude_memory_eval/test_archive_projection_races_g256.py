# ==========================================================
# Projet      : Eidolon Memory Engine
# Organisation: Eidolon Core Technologies (ECT)
# Fichier     : tests/claude_memory_eval/test_archive_projection_races_g256.py
# Description : Courses de la projection d'archives : lecture/preuve, révocation, éviction (Claude, G256-5)
# Standard    : Eidolon Presentation Standard v1
# ==========================================================
"""Synthetic archive only, in-memory projection; the real Qdrant adapter is untouched. A passage is cited
only from the current canonical bytes, and superseded points never hide the current ones."""
from dataclasses import replace

import pytest

import tests.claude_memory_eval.archive_passage_projection as projection
from core.retrieval.contextual import ContextualRecall
from tests.claude_memory_eval.archive_passage_projection import ArchivePassageProjection
from tests.test_archive_chunks import archive, store_archive
from tests.test_contextual_recall import backend

TEXTS = ["Question sur la sauvegarde.", "Les clichés sont copiés chaque nuit sur le disque externe.",
         "Autre sujet : la recette des crêpes."]


def by_revision(first):
    # The oldest points rank first: the worst case for the candidate limit.
    return lambda text, point: (1.0 if point["revision"] == first else 0.5) + \
        (0.01 if point["passage"]["message_index"] == 1 else 0.0)


def update(data, original, texts, revision):
    new = replace(original, content=archive(texts), revision=revision)
    data.update("archive", new, previous_revision=revision - 1)
    return new


def test_superseded_points_do_not_fill_the_candidate_limit(tmp_path):
    data = backend(tmp_path)
    original = store_archive(data, TEXTS)
    index = ArchivePassageProjection(data.persistent_root, score=by_revision(1))
    index.project("archive")
    update(data, original, [TEXTS[0], "Les clichés partent maintenant vers le NAS.", TEXTS[2]], 2)
    index.project("archive")
    assert len(index.points) == 6  # nothing deleted: old points are kept, not served
    result = ContextualRecall(data, index=index, candidate_limit=3).recall("clichés", max_items=1)
    assert [i.content for i in result.items] == ["Les clichés partent maintenant vers le NAS."]
    assert not result.excluded_counts.get("INDEX_REVISION_MISMATCH")


def test_bytes_changed_after_projection_at_the_same_revision_are_never_cited(tmp_path):
    data = backend(tmp_path)
    store_archive(data, TEXTS)
    index = ArchivePassageProjection(data.persistent_root, score=by_revision(1))
    index.project("archive")
    leaf = data.persistent_root / "archive.md"
    raw = leaf.read_text(encoding="utf-8")
    assert raw.count("chaque nuit") == 1
    leaf.write_text(raw.replace("chaque nuit", "chaque mois"), encoding="utf-8")  # hand edit, no new revision
    result = ContextualRecall(data, index=index).recall("clichés")
    assert all("chaque" not in i.content for i in result.items if i.information_id == "archive")
    assert result.excluded_counts.get("INDEX_DIGEST_MISMATCH", 0) >= 1


def test_a_change_between_the_canonical_read_and_point_storage_is_detected(tmp_path, monkeypatch):
    data = backend(tmp_path)
    original = store_archive(data, TEXTS)
    real = projection.chunk_messages

    def racing(content, **limits):  # the archive changes once the bytes have been read and hashed
        update(data, original, [TEXTS[0], "Version écrite pendant la projection.", TEXTS[2]], 2)
        return real(content, **limits)
    monkeypatch.setattr(projection, "chunk_messages", racing)
    index = ArchivePassageProjection(data.persistent_root, score=by_revision(1))
    index.project("archive")
    monkeypatch.setattr(projection, "chunk_messages", real)
    assert {p["revision"] for p in index.points.values()} == {1}  # proofs describe what was read
    result = ContextualRecall(data, index=index).recall("clichés")
    assert not [i for i in result.items if i.information_id == "archive"]
    assert result.excluded_counts.get("INDEX_REVISION_MISMATCH", 0) >= 1
    index.project("archive")  # the next projection serves the new revision
    items = ContextualRecall(data, index=index).recall("Version").items
    assert [i.content for i in items] == ["Version écrite pendant la projection."]


def test_a_revoked_archive_stops_being_served_without_deleting_points(tmp_path):
    data = backend(tmp_path)
    store_archive(data, TEXTS)
    index = ArchivePassageProjection(data.persistent_root, score=by_revision(1))
    index.project("archive")
    (data.persistent_root / "archive.md").rename(tmp_path / "revoked.md")
    with pytest.raises(ValueError, match="absent or unsafe"):
        index.project("archive")
    assert len(index.points) == 3 and index.query("clichés", limit=10) == []
    assert ContextualRecall(data, index=index).recall("clichés").items == ()


def test_an_archive_emptied_of_messages_serves_nothing(tmp_path):
    data = backend(tmp_path)
    original = store_archive(data, TEXTS)
    index = ArchivePassageProjection(data.persistent_root, score=by_revision(1))
    index.project("archive")
    update(data, original, ["", "  "], 2)
    assert index.project("archive") == ()
    assert index.query("clichés", limit=10) == []


def test_long_messages_are_covered_by_bounded_overlapping_passages(tmp_path):
    words = " ".join(f"mot{n:04d}" for n in range(700))  # ~5 600 characters, one message
    data = backend(tmp_path)
    store_archive(data, ["q", words])
    index = ArchivePassageProjection(data.persistent_root, score=lambda t, p: 1.0)
    refs = sorted((index.points[p]["passage"] for p in index.project("archive")
                   if index.points[p]["passage"]["message_index"] == 1), key=lambda r: r["start"])
    assert refs[0]["start"] == 0 and refs[-1]["end"] == len(words)
    for a, b in zip(refs, refs[1:]):
        assert a["end"] - a["start"] <= 1200 and a["start"] < b["start"] <= a["end"]
        assert a["end"] - b["start"] <= 160  # overlap bound


@pytest.mark.parametrize("ref", [{"message_index": 9, "start": 0, "end": 3},
                                 {"message_index": 1, "start": 0, "end": 999}])
def test_one_out_of_bounds_passage_is_excluded_and_does_not_fail_the_whole_recall(tmp_path, ref):
    # Killed nowhere else: without the candidate-level check this point raised out of recall().
    from core.indexing.port import IndexHit
    data = backend(tmp_path)
    store_archive(data, TEXTS)

    class Index:
        def query(self, text, *, limit):
            return [IndexHit("archive", 1.0, {"revision": 1, "passage": dict(ref)})]
    result = ContextualRecall(data, index=Index()).recall("clichés")
    assert result.items == () and result.excluded_counts == {"INDEX_PASSAGE_UNRESOLVED": 1}
