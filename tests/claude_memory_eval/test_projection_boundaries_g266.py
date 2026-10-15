# ==========================================================
# Projet      : Eidolon Memory Engine
# Organisation: Eidolon Core Technologies (ECT)
# Fichier     : tests/claude_memory_eval/test_projection_boundaries_g266.py
# Description : Projection : plafond du découpeur, retour à une ancienne empreinte, archive absente (Claude, G266-8)
# Standard    : Eidolon Presentation Standard v1
# ==========================================================
"""Synthetic archives, in-memory projection; experimental, no compaction, no production wiring."""
import pytest

import tests.claude_memory_eval.archive_passage_projection as proj
from tests.claude_memory_eval.test_archive_projection_budget_g258 import revise, store, words
from tests.test_contextual_recall import backend


CEIL = 10000                                                         # chunk_messages default ceiling


def projection(data, **budget):
    return proj.ArchivePassageProjection(data.persistent_root, score=lambda t, p: 1.0, **budget)


def many(n):
    return [f"m{i}" for i in range(n)]                               # one passage per message


def refused(index, name):
    with pytest.raises(proj.ProjectionBudgetExceeded) as caught:
        index.project(name)
    return caught.value.code


@pytest.mark.parametrize("messages, budget, outcome", [
    (CEIL, {}, CEIL),                       # exactly the ceiling: accepted
    (CEIL + 1, {}, "CHUNKER_CEILING"),
    (CEIL + 1, {"max_passages_per_archive": CEIL}, "CHUNKER_CEILING"),
    (CEIL, {"max_passages_per_archive": CEIL - 1}, "PASSAGES_PER_ARCHIVE"),
    (CEIL, {"max_points": CEIL - 1}, "POINTS"),
    (CEIL, {"max_points": CEIL}, CEIL),
])
def test_near_the_chunker_ceiling_each_limit_has_its_own_code(tmp_path, messages, budget, outcome):
    assert getattr(proj, "CHUNKER_CEILING", None) == CEIL               # the ceiling is named, not implicit
    data = backend(tmp_path)
    store(data, "big", many(messages))
    index = projection(data, **budget)
    if isinstance(outcome, int):
        assert len(index.project("big")) == outcome
    else:
        assert refused(index, "big") == outcome and index.points == {} and index.current == {}


def test_returning_to_an_older_digest_reuses_its_points_even_with_a_full_budget(tmp_path):
    data = backend(tmp_path)
    memory = store(data, "a", ["q", words(300, "v1")])
    leaf = data.persistent_root / "a.md"
    v1 = leaf.read_bytes()
    index = projection(data, max_points=6)
    first = index.project("a")
    revise(data, memory, ["q", words(300, "v2")])
    index.project("a")
    assert len(index.points) == 6                                    # budget full
    leaf.write_bytes(v1)                                             # canonical bytes back to revision 1
    assert index.project("a") == first and len(index.points) == 6    # nothing new, accepted
    assert {h.ranking["revision"] for h in index.query("q", limit=10)} == {1}


def test_an_archive_absent_then_restored_is_served_again_without_new_points(tmp_path):
    data = backend(tmp_path)
    store(data, "a", ["q", words(300, "v1")])
    leaf = data.persistent_root / "a.md"
    index = projection(data, max_points=3)
    ids = index.project("a")
    leaf.rename(tmp_path / "away.md")
    with pytest.raises(ValueError):
        index.project("a")
    assert index.query("q", limit=10) == [] and len(index.points) == 3
    (tmp_path / "away.md").rename(leaf)
    assert index.project("a") == ids and index.query("q", limit=10)


def test_a_refusal_never_changes_what_was_served(tmp_path):
    data = backend(tmp_path)
    memory = store(data, "a", ["q", words(300, "v1")])
    index = projection(data, max_points=3)
    index.project("a")
    before = (dict(index.points), dict(index.current), [h.ranking for h in index.query("q", limit=10)])
    revise(data, memory, many(50))
    assert refused(index, "a") == "POINTS"
    assert (index.points, index.current, [h.ranking for h in index.query("q", limit=10)]) == before
