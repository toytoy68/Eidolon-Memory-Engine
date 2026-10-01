"""Bounded, structured context for a caller to render under its own policy."""

from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Callable

from core.backend.interface import MemoryBackend
from core.information.models import EpistemicStatus


@dataclass(frozen=True)
class ContextItem:
    information_id: str
    revision: int
    content: str
    score: float | None
    truncated: bool
    epistemic_status: str | None
    operational_state: str | None
    confidence: str | None
    ranking: dict | None = None
    token_count: int | None = None
    importance: str | None = None
    retention: str | None = None
    valid_from: str | None = None
    valid_until: str | None = None
    content_format: str = "text"


@dataclass(frozen=True)
class ContextBundle:
    query: str
    items: tuple[ContextItem, ...]
    used_chars: int
    used_tokens: int | None = None


class ContextAssembler:
    """Select text from ranked search results without writing or formatting a prompt."""

    def __init__(self, backend: MemoryBackend) -> None:
        self.backend = backend

    def assemble(self, query: str, *, max_items: int = 5,
                 max_chars: int = 4000, max_item_chars: int = 1000,
                 ranking: str | None = None, max_tokens: int | None = None,
                 token_counter: Callable[[str], int] | None = None,
                 allowed_epistemic_statuses: set[str | None] | frozenset[str | None] | None = None,
                 include_structured_content: bool = False,
                 candidate_filter: Callable | None = None) -> ContextBundle:
        if candidate_filter is not None and not callable(candidate_filter):
            raise ValueError("candidate_filter must be callable")
        if not isinstance(query, str) or not query.strip():
            raise ValueError("query must be nonempty text")
        if any(type(value) is not int or value < 1
               for value in (max_items, max_chars, max_item_chars)):
            raise ValueError("context limits must be positive integers")
        if ranking not in (None, "lexical_v1"):
            raise ValueError("unknown context ranking")
        if type(include_structured_content) is not bool:
            raise ValueError("include_structured_content must be a boolean")
        if (max_tokens is None) != (token_counter is None):
            raise ValueError("max_tokens and token_counter must be provided together")
        if max_tokens is not None and (type(max_tokens) is not int or max_tokens < 1
                                       or not callable(token_counter)):
            raise ValueError("invalid token budget")
        if allowed_epistemic_statuses is not None and (
            not isinstance(allowed_epistemic_statuses, (set, frozenset))
            or any(status is not None and
                   (type(status) is not str or status not in {item.value for item in EpistemicStatus})
                   for status in allowed_epistemic_statuses)
        ):
            raise ValueError("invalid epistemic status filter")
        selected_statuses = (frozenset(allowed_epistemic_statuses)
                             if allowed_epistemic_statuses is not None else None)

        items = []
        seen = set()
        remaining = max_chars
        remaining_tokens = max_tokens
        # Page past hits with no usable text while bounding each search response.
        page_size = 100
        offset = 0
        seen_pages = set()
        while remaining and len(items) < max_items and remaining_tokens != 0:
            options = {"limit": page_size, "offset": offset}
            if ranking is not None:
                options["ranking"] = ranking
            candidates = self.backend.search(query, options)
            page_ids = tuple(result.memory.information_id for result in candidates)
            if page_ids in seen_pages:
                break
            seen_pages.add(page_ids)
            for result in candidates:
                memory = result.memory
                if memory.information_id in seen:
                    continue
                seen.add(memory.information_id)
                if (selected_statuses is not None
                        and self._label(memory.metadata, "epistemic_status")
                        not in selected_statuses):
                    continue
                if candidate_filter is not None:
                    accepted = candidate_filter(memory)
                    if type(accepted) is not bool:
                        raise ValueError("candidate_filter must return a boolean")
                    if not accepted:
                        continue
                content = memory.content
                content_format = "text"
                if include_structured_content and isinstance(content, (dict, list)):
                    try:
                        content = json.dumps(content, ensure_ascii=False, sort_keys=True,
                                             separators=(",", ":"), allow_nan=False)
                    except (TypeError, ValueError):
                        continue
                    content_format = "json"
                if not isinstance(content, str) or not content:
                    continue
                length = min(len(content), max_item_chars, remaining)
                token_count = None
                if remaining_tokens is not None:
                    length, token_count = self._fit_tokens(
                        content, length, remaining_tokens, token_counter)
                    if length == 0:
                        continue
                items.append(ContextItem(
                    information_id=memory.information_id,
                    revision=memory.revision,
                    content=content[:length],
                    score=result.score,
                    truncated=length < len(content),
                    epistemic_status=self._label(memory.metadata, "epistemic_status"),
                    operational_state=self._label(memory.metadata, "operational_state"),
                    confidence=self._label(memory.metadata, "confidence"),
                    ranking=result.metadata.get("ranking") if ranking is not None else None,
                    token_count=token_count,
                    importance=self._label(memory.metadata, "importance"),
                    retention=self._label(memory.metadata, "retention"),
                    valid_from=self._label(memory.temporal, "valid_from"),
                    valid_until=self._label(memory.temporal, "valid_until"),
                    content_format=content_format,
                ))
                remaining -= length
                if remaining_tokens is not None:
                    remaining_tokens -= token_count
                if len(items) == max_items or remaining == 0 or remaining_tokens == 0:
                    break
            if len(candidates) < page_size:
                break
            offset += len(candidates)
        return ContextBundle(query=query, items=tuple(items), used_chars=max_chars - remaining,
                             used_tokens=(max_tokens - remaining_tokens)
                             if max_tokens is not None else None)

    @staticmethod
    def _fit_tokens(content: str, length: int, budget: int,
                    counter: Callable[[str], int]) -> tuple[int, int]:
        """Find a prefix within the token budget; counter counts isolated text."""
        def count(size: int) -> int:
            value = counter(content[:size])
            if type(value) is not int or value < 0:
                raise ValueError("token counter must return a nonnegative integer")
            return value

        full_count = count(length)
        if full_count <= budget:
            return length, full_count
        low, high = 0, length
        while low + 1 < high:
            mid = (low + high) // 2
            if count(mid) <= budget:
                low = mid
            else:
                high = mid
        return low, count(low)

    @staticmethod
    def _label(metadata: dict, key: str) -> str | None:
        value = metadata.get(key)
        return value if isinstance(value, str) else None
