from dataclasses import dataclass

import pytest

from core.backend.filesystem import FilesystemBackend
from core.backend.models import Memory, SearchResult
from core.retrieval import ContextAssembler


def test_context_from_real_files_is_bounded_and_traceable(tmp_path):
    backend = FilesystemBackend(tmp_path / "persistent", tmp_path / "history")
    backend.store(Memory("info-1", content="alpha " * 10,
                         metadata={"epistemic_status": "REFUTED",
                                   "operational_state": "ACTIVE", "confidence": "LOW"}))
    backend.store(Memory("info-2", content="alpha second"))
    bundle = ContextAssembler(backend).assemble(
        "alpha", max_items=2, max_chars=17, max_item_chars=12)
    assert [(item.information_id, item.revision, item.content, item.truncated)
            for item in bundle.items] == [
        ("info-1", 1, "alpha alpha ", True),
        ("info-2", 1, "alpha", True),
    ]
    assert bundle.used_chars == 17
    assert (bundle.items[0].epistemic_status, bundle.items[0].operational_state,
            bundle.items[0].confidence) == ("REFUTED", "ACTIVE", "LOW")
    assert bundle.items[1].epistemic_status is None
    assert backend.get("info-1").content == "alpha " * 10


def test_context_skips_nontext_empty_and_duplicate_search_hits():
    @dataclass
    class FakeBackend:
        def search(self, query, options):
            assert options["limit"] >= 100
            return [
                SearchResult(Memory("structured", content={"secret": "value"}), 1.0),
                SearchResult(Memory("empty", content=""), 0.9),
                SearchResult(Memory("valid", revision=3, content="usable"), 0.8),
                SearchResult(Memory("valid", revision=2, content="duplicate"), 0.7),
            ]

    bundle = ContextAssembler(FakeBackend()).assemble("query")
    assert [(item.information_id, item.revision, item.content)
            for item in bundle.items] == [("valid", 3, "usable")]
    assert bundle.used_chars == 6


@pytest.mark.parametrize("kwargs", [
    {"query": "  "}, {"query": None}, {"query": "x", "max_items": True},
    {"query": "x", "max_chars": 0}, {"query": "x", "max_item_chars": -1},
])
def test_context_rejects_invalid_limits_and_queries(kwargs):
    with pytest.raises(ValueError):
        ContextAssembler(None).assemble(**kwargs)
