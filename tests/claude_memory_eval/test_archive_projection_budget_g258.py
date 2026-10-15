# ==========================================================
# Projet      : Eidolon Memory Engine
# Organisation: Eidolon Core Technologies (ECT)
# Fichier     : tests/claude_memory_eval/test_archive_projection_budget_g258.py
# Description : Projection de passages : limites cumulées, archives et révisions multiples (Claude, G258-9)
# Standard    : Eidolon Presentation Standard v1
# ==========================================================
"""Synthetic archives only, in-memory; no model, no private corpus, no deletion."""
from dataclasses import replace

import pytest

from core.backend.models import Memory
from core.retrieval.contextual import ContextualRecall
from tests.claude_memory_eval.archive_passage_projection import ArchivePassageProjection, ProjectionBudgetExceeded
from tests.test_archive_chunks import archive
from tests.test_contextual_recall import backend


def store(data, name, texts):
    memory = Memory(name, content=archive(texts),
                    metadata={'archive_kind': 'conversation', 'epistemic_status': 'UNVERIFIED'},
                    provenance={'importer': 'chatgpt-archive-v1'})
    data.store(memory)
    return memory


def revise(data, memory, texts):
    new = replace(memory, content=archive(texts), revision=memory.revision + 1)
    data.update(memory.information_id, new, previous_revision=memory.revision)
    return new


def words(n, tag):
    return " ".join(f"{tag}{i:04d}" for i in range(n))     # 8 characters + space per word


def test_points_accumulate_with_revisions_and_are_reported(tmp_path):
    data = backend(tmp_path)
    archives = {f"a{n}": store(data, f"a{n}", ["q", words(300, f"r1m{n}")]) for n in range(5)}
    index = ArchivePassageProjection(data.persistent_root, score=lambda t, p: 1.0)
    per_revision = [sum(len(index.project(name)) for name in archives)]
    assert index.stats() == dict(points=per_revision[0], served=per_revision[0], superseded=0, archives=5,
                                 unservable=0)
    for r in (2, 3):
        for name in archives:
            archives[name] = revise(data, archives[name], ["q", words(300, f"r{r}m{name}")])
        per_revision.append(sum(len(index.project(name)) for name in archives))
    stats = index.stats()
    assert stats["served"] == per_revision[-1]
    assert stats["superseded"] == sum(per_revision[:-1]) and stats["points"] == sum(per_revision)
    assert all(index.project(name) for name in archives) and index.stats() == stats   # same bytes: no growth


def test_the_per_archive_budget_refuses_before_any_change(tmp_path):
    data = backend(tmp_path)
    small = store(data, "small", ["q", "réponse courte"])
    store(data, "large", ["q", words(1000, "x")])                     # ~9 000 chars: several passages
    index = ArchivePassageProjection(data.persistent_root, score=lambda t, p: 1.0, max_passages_per_archive=3)
    assert len(index.project("small")) == 2
    before = (dict(index.points), dict(index.current))
    with pytest.raises(ProjectionBudgetExceeded) as caught:
        index.project("large")
    assert caught.value.code == "PASSAGES_PER_ARCHIVE" and (index.points, index.current) == before
    revise(data, small, ["q", words(1000, "y")])                      # the new revision is too large too
    with pytest.raises(ProjectionBudgetExceeded):
        index.project("small")
    hits = index.query("q", limit=10)
    assert hits and all(h.ranking["revision"] == 1 for h in hits)    # the previous projection stays served


def test_the_total_budget_counts_superseded_points_and_a_refusal_changes_nothing(tmp_path):
    data = backend(tmp_path)
    memory = store(data, "a", ["q", words(300, "v1")])
    index = ArchivePassageProjection(data.persistent_root, score=lambda t, p: 1.0, max_points=5)
    first = len(index.project("a"))
    assert first == 3
    revise(data, memory, ["q", words(300, "v2")])
    before = (dict(index.points), dict(index.current))
    with pytest.raises(ProjectionBudgetExceeded) as caught:            # 3 stored + 3 new > 5
        index.project("a")
    assert caught.value.code == "POINTS" and (index.points, index.current) == before
    # Stale but served: recall refuses the old revision instead of citing it.
    result = ContextualRecall(data, index=index).recall("v10001")
    assert result.items == () and result.excluded_counts.get("INDEX_REVISION_MISMATCH", 0) >= 1


@pytest.mark.parametrize("bad", [0, -1, True, 1.5, "10"])
def test_invalid_budgets_are_refused(tmp_path, bad):
    with pytest.raises(ValueError):
        ArchivePassageProjection(tmp_path, score=lambda t, p: 1.0, max_points=bad)
    with pytest.raises(ValueError):
        ArchivePassageProjection(tmp_path, score=lambda t, p: 1.0, max_passages_per_archive=bad)
