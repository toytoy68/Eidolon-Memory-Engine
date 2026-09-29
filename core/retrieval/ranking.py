"""Deterministic lexical ranking signals, independent of agents and indexes."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import re
from typing import Any
import unicodedata


def terms(text: str) -> tuple[str, ...]:
    normalized = unicodedata.normalize("NFC", text.casefold())
    return tuple(re.findall(r"\w+", normalized, flags=re.UNICODE))


def _text_values(value: Any):
    if isinstance(value, str):
        yield value
    elif type(value) in (int, float):
        yield str(value)
    elif isinstance(value, dict):
        for child in value.values():
            yield from _text_values(child)
    elif isinstance(value, (list, tuple)):
        for child in value:
            yield from _text_values(child)


@dataclass(frozen=True)
class LexicalRanking:
    score: float
    coverage: float
    content_coverage: float
    phrase_in_content: bool
    frequency: float

    def explanation(self) -> dict[str, float | bool | str]:
        return {
            "policy": "lexical_v1",
            "coverage": self.coverage,
            "content_coverage": self.content_coverage,
            "phrase_in_content": self.phrase_in_content,
            "frequency": self.frequency,
        }


def lexical_ranking(query: str, content: object, information_id: str,
                    metadata: dict[str, Any], auxiliary: object = None) -> LexicalRanking:
    """Score term coverage and capped frequency, without epistemic boosts."""
    query_terms = terms(query)
    ordered = tuple(dict.fromkeys(query_terms))
    if not ordered:
        return LexicalRanking(0.0, 0.0, 0.0, False, 0.0)
    content_terms = terms(" ".join(_text_values(content)))
    auxiliary_terms = terms(" ".join((information_id, *_text_values(metadata),
                                      *_text_values(auxiliary))))
    counts = Counter(content_terms)
    counts.update(auxiliary_terms)
    matched = sum(term in counts for term in ordered)
    content_matched = sum(term in content_terms for term in ordered)
    phrase = any(content_terms[index:index + len(query_terms)] == query_terms
                 for index in range(len(content_terms) - len(query_terms) + 1))
    frequency = sum(min(counts[term], 3) for term in ordered) / (3 * len(ordered))
    coverage = matched / len(ordered)
    content_coverage = content_matched / len(ordered)
    score = (0.55 * coverage + 0.25 * content_coverage
             + 0.15 * phrase + 0.05 * frequency)
    return LexicalRanking(score, coverage, content_coverage, phrase, frequency)
