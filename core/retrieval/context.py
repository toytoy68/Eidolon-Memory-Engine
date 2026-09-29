"""Bounded, structured context for a caller to render under its own policy."""

from __future__ import annotations

from dataclasses import dataclass

from core.backend.interface import MemoryBackend


@dataclass(frozen=True)
class ContextItem:
    information_id: str
    revision: int
    content: str
    score: float | None
    truncated: bool


@dataclass(frozen=True)
class ContextBundle:
    query: str
    items: tuple[ContextItem, ...]
    used_chars: int


class ContextAssembler:
    """Select text from ranked search results without writing or formatting a prompt."""

    def __init__(self, backend: MemoryBackend) -> None:
        self.backend = backend

    def assemble(self, query: str, *, max_items: int = 5,
                 max_chars: int = 4000, max_item_chars: int = 1000) -> ContextBundle:
        if not isinstance(query, str) or not query.strip():
            raise ValueError("query must be nonempty text")
        if any(type(value) is not int or value < 1
               for value in (max_items, max_chars, max_item_chars)):
            raise ValueError("context limits must be positive integers")

        items = []
        seen = set()
        remaining = max_chars
        # Allow room for search hits without text or repeated identifiers.
        candidates = self.backend.search(query, {"limit": max(100, max_items * 4)})
        for result in candidates:
            memory = result.memory
            if memory.information_id in seen or not isinstance(memory.content, str):
                continue
            seen.add(memory.information_id)
            if not memory.content:
                continue
            length = min(len(memory.content), max_item_chars, remaining)
            items.append(ContextItem(
                information_id=memory.information_id,
                revision=memory.revision,
                content=memory.content[:length],
                score=result.score,
                truncated=length < len(memory.content),
            ))
            remaining -= length
            if len(items) == max_items or remaining == 0:
                break
        return ContextBundle(query=query, items=tuple(items), used_chars=max_chars - remaining)
