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


def test_context_opt_in_ranking_keeps_explanation_and_status_separate(tmp_path):
    backend = FilesystemBackend(tmp_path / "persistent", tmp_path / "history")
    backend.store(Memory("metadata", content="unrelated",
                         metadata={"topic": "cuivre pompe", "epistemic_status": "CONFIRMED"}))
    backend.store(Memory("content", content="cuivre pompe",
                         metadata={"epistemic_status": "REFUTED"}))
    bundle = ContextAssembler(backend).assemble("cuivre pompe", ranking="lexical_v1")
    assert [item.information_id for item in bundle.items] == ["content", "metadata"]
    assert bundle.items[0].epistemic_status == "REFUTED"
    assert bundle.items[0].ranking["content_coverage"] == 1
    assert bundle.items[1].ranking["content_coverage"] == 0


def test_context_exposes_retention_and_validity_without_ranking_by_them(tmp_path):
    backend = FilesystemBackend(tmp_path / "persistent", tmp_path / "history")
    backend.store(Memory("a", content="alpha",
                         metadata={"importance": "CRITICAL", "retention": "PERMANENT"},
                         temporal={"valid_from": "2026-01-01T00:00:00Z",
                                   "valid_until": "2026-06-01T00:00:00Z"}))
    backend.store(Memory("b", content="alpha",
                         metadata={"importance": "LOW", "retention": "TEMPORARY"}))
    bundle = ContextAssembler(backend).assemble("alpha", ranking="lexical_v1")
    assert [item.information_id for item in bundle.items] == ["a", "b"]
    assert bundle.items[0].score == bundle.items[1].score
    assert (bundle.items[0].importance, bundle.items[0].retention,
            bundle.items[0].valid_from, bundle.items[0].valid_until) == (
                "CRITICAL", "PERMANENT", "2026-01-01T00:00:00Z",
                "2026-06-01T00:00:00Z")


def test_context_respects_injected_token_budget_and_char_limit(tmp_path):
    backend = FilesystemBackend(tmp_path / "persistent", tmp_path / "history")
    backend.store(Memory("first", content="abcdef"))
    backend.store(Memory("second", content="ghijkl"))
    bundle = ContextAssembler(backend).assemble(
        "first second", max_chars=20, max_item_chars=5,
        max_tokens=7, token_counter=len)
    assert [(item.content, item.token_count, item.truncated) for item in bundle.items] == [
        ("abcde", 5, True), ("gh", 2, True),
    ]
    assert bundle.used_chars == bundle.used_tokens == 7


def test_context_skips_items_without_a_token_fitting_the_budget(tmp_path):
    backend = FilesystemBackend(tmp_path / "persistent", tmp_path / "history")
    backend.store(Memory("first", content="alpha"))
    bundle = ContextAssembler(backend).assemble(
        "alpha", max_tokens=1, token_counter=lambda text: 2 if text else 0)
    assert bundle.items == ()
    assert bundle.used_tokens == 0


def test_context_rejects_invalid_token_counter_result(tmp_path):
    backend = FilesystemBackend(tmp_path / "persistent", tmp_path / "history")
    backend.store(Memory("first", content="alpha"))
    with pytest.raises(ValueError, match="token counter"):
        ContextAssembler(backend).assemble("alpha", max_tokens=1,
                                           token_counter=lambda text: True)


def test_explicit_epistemic_filter_pages_past_excluded_hits():
    class PagedBackend:
        def search(self, query, options):
            hits = [SearchResult(Memory(f"refuted-{i}", content="alpha",
                                        metadata={"epistemic_status": "REFUTED"}), 1.0)
                    for i in range(100)]
            hits.append(SearchResult(Memory("confirmed", content="alpha",
                                            metadata={"epistemic_status": "CONFIRMED"}), 0.5))
            offset = options["offset"]
            return hits[offset:offset + options["limit"]]

    assembler = ContextAssembler(PagedBackend())
    assert [item.information_id for item in assembler.assemble("alpha", max_items=1).items] == [
        "refuted-0",
    ]
    filtered = assembler.assemble("alpha", max_items=1,
                                  allowed_epistemic_statuses={"CONFIRMED"})
    assert [item.information_id for item in filtered.items] == ["confirmed"]


def test_explicit_epistemic_filter_can_include_missing_status(tmp_path):
    backend = FilesystemBackend(tmp_path / "persistent", tmp_path / "history")
    backend.store(Memory("unknown", content="alpha"))
    assert ContextAssembler(backend).assemble(
        "alpha", allowed_epistemic_statuses={None}).items[0].information_id == "unknown"
    with pytest.raises(ValueError, match="epistemic status filter"):
        ContextAssembler(backend).assemble("alpha", allowed_epistemic_statuses={"VALID"})


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


def test_context_pages_past_full_page_of_unusable_hits():
    class PagedBackend:
        def search(self, query, options):
            hits = [SearchResult(Memory(f"empty-{i}", content=""), 1.0)
                    for i in range(100)]
            hits.append(SearchResult(Memory("useful", content="answer"), 0.5))
            offset = options["offset"]
            return hits[offset:offset + options["limit"]]

    bundle = ContextAssembler(PagedBackend()).assemble("query", max_items=1)
    assert [(item.information_id, item.content) for item in bundle.items] == [
        ("useful", "answer"),
    ]


def test_context_page_size_stays_bounded_for_large_item_limit():
    class RecordingBackend:
        def search(self, query, options):
            assert options == {"limit": 100, "offset": 0}
            return []

    assert ContextAssembler(RecordingBackend()).assemble("query", max_items=10000).items == ()


def test_context_stops_if_backend_repeats_a_full_page():
    class BrokenPagination:
        calls = 0

        def search(self, query, options):
            self.calls += 1
            return [SearchResult(Memory(f"empty-{i}", content=""), 1.0)
                    for i in range(100)]

    backend = BrokenPagination()
    assert ContextAssembler(backend).assemble("query").items == ()
    assert backend.calls == 2


def test_context_stops_if_backend_alternates_full_pages():
    class BrokenPagination:
        calls = 0

        def search(self, query, options):
            self.calls += 1
            prefix = "a" if self.calls % 2 else "b"
            return [SearchResult(Memory(f"{prefix}-{i}", content=""), 1.0)
                    for i in range(100)]

    backend = BrokenPagination()
    assert ContextAssembler(backend).assemble("query").items == ()
    assert backend.calls == 3


def test_filesystem_search_offset_pages_ranked_results(tmp_path):
    backend = FilesystemBackend(tmp_path / "persistent", tmp_path / "history")
    for index in range(3):
        backend.store(Memory(f"info-{index}", content="alpha"))
    first = backend.search("alpha", {"limit": 2})
    second = backend.search("alpha", {"limit": 2, "offset": 2})
    assert [hit.memory.information_id for hit in first + second] == [
        "info-0", "info-1", "info-2",
    ]


@pytest.mark.parametrize("options", [
    {"limit": 0}, {"limit": True}, {"limit": "5"},
    {"offset": -1}, {"offset": False}, {"offset": 1.5},
])
def test_filesystem_search_rejects_invalid_pagination(tmp_path, options):
    backend = FilesystemBackend(tmp_path / "persistent", tmp_path / "history")
    with pytest.raises(ValueError):
        backend.search("alpha", options)


@pytest.mark.parametrize("kwargs", [
    {"query": "  "}, {"query": None}, {"query": "x", "max_items": True},
    {"query": "x", "max_chars": 0}, {"query": "x", "max_item_chars": -1},
    {"query": "x", "max_tokens": 10},
    {"query": "x", "token_counter": len},
    {"query": "x", "max_tokens": True, "token_counter": len},
])
def test_context_rejects_invalid_limits_and_queries(kwargs):
    with pytest.raises(ValueError):
        ContextAssembler(None).assemble(**kwargs)
