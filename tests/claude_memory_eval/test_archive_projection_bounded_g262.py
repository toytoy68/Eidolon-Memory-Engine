# ==========================================================
# Projet      : Eidolon Memory Engine
# Organisation: Eidolon Core Technologies (ECT)
# Fichier     : tests/claude_memory_eval/test_archive_projection_bounded_g262.py
# Description : Budget de projection : arrêt borné avant de matérialiser une grande archive (Claude, G262-8)
# Standard    : Eidolon Presentation Standard v1
# ==========================================================
"""Synthetic archives only, in-memory; still experimental, no compaction and no deletion."""
import pytest

import tests.claude_memory_eval.archive_passage_projection as proj
from tests.claude_memory_eval.test_archive_projection_budget_g258 import revise, store, words
from tests.test_contextual_recall import backend


@pytest.fixture
def spy(monkeypatch):
    calls = []
    real = proj.chunk_messages

    def counting(*args, **kwargs):
        try:
            out = real(*args, **kwargs)
        except ValueError:
            calls.append((kwargs.get("max_chunks"), "stopped"))
            raise
        calls.append((kwargs.get("max_chunks"), len(out)))
        return out
    monkeypatch.setattr(proj, "chunk_messages", counting)
    return calls


@pytest.mark.parametrize("budget, code", [(dict(max_points=1), "POINTS"),
                                          (dict(max_passages_per_archive=3), "PASSAGES_PER_ARCHIVE")])
def test_a_large_archive_is_refused_after_a_bounded_amount_of_chunking(tmp_path, spy, budget, code):
    data = backend(tmp_path)
    store(data, "big", ["q", words(20_000, "w")])                 # ~180 000 characters, ~126 passages
    index = proj.ArchivePassageProjection(data.persistent_root, score=lambda t, p: 1.0, **budget)
    with pytest.raises(proj.ProjectionBudgetExceeded) as caught:
        index.project("big")
    assert caught.value.code == code and index.points == {} and index.current == {}
    bound = 2 if "max_points" in budget else 4
    assert spy == [(bound, "stopped")]                            # never the whole archive


def test_the_previous_projection_stays_served_after_a_bounded_refusal(tmp_path, spy):
    data = backend(tmp_path)
    memory = store(data, "a", ["q", words(300, "v1")])
    index = proj.ArchivePassageProjection(data.persistent_root, score=lambda t, p: 1.0, max_points=5)
    first = index.project("a")
    revise(data, memory, ["q", words(20_000, "v2")])
    with pytest.raises(proj.ProjectionBudgetExceeded):
        index.project("a")
    assert spy[-1] == (5 - len(first) + 1, "stopped")
    assert {h.ranking["revision"] for h in index.query("q", limit=10)} == {1}


def test_reprojecting_the_same_bytes_does_no_chunking_even_when_the_budget_is_full(tmp_path, spy):
    data = backend(tmp_path)
    store(data, "a", ["q", words(300, "v1")])
    index = proj.ArchivePassageProjection(data.persistent_root, score=lambda t, p: 1.0, max_points=3)
    ids = index.project("a")
    assert len(ids) == 3 and len(spy) == 1
    assert index.project("a") == ids and len(spy) == 1             # full budget, same bytes: accepted, no work


def test_an_ample_budget_never_refuses_and_gives_the_same_points(tmp_path):
    data = backend(tmp_path)
    store(data, "a", ["q", words(3_000, "x")])
    free = proj.ArchivePassageProjection(data.persistent_root, score=lambda t, p: 1.0)
    bounded = proj.ArchivePassageProjection(data.persistent_root, score=lambda t, p: 1.0, max_points=10_000,
                                            max_passages_per_archive=10_000)
    assert free.project("a") == bounded.project("a")


def test_documented_limit_whitespace_chunks_make_the_refusal_conservative(tmp_path):
    data = backend(tmp_path)
    store(data, "a", ["   ", "\n\t", "réel"])                     # 3 chunks, only 1 becomes a point
    index = proj.ArchivePassageProjection(data.persistent_root, score=lambda t, p: 1.0, max_points=1)
    with pytest.raises(proj.ProjectionBudgetExceeded):             # would fit, refused: never permissive
        index.project("a")
    roomy = proj.ArchivePassageProjection(data.persistent_root, score=lambda t, p: 1.0, max_points=2)
    assert len(roomy.project("a")) == 1                            # bound 3 covers the 3 chunks: accepted
