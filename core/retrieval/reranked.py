# ==========================================================
# Projet      : Eidolon Memory Engine
# Organisation: Eidolon Core Technologies (ECT)
# Fichier     : core/retrieval/reranked.py
# Description : Optional bounded reranking after canonical policy filtering.
# Standard    : Eidolon Presentation Standard v1
# ==========================================================
"""Scores order eligible excerpts; they never establish truth or change status."""
from dataclasses import replace
import math

class RerankedRecall:
    def __init__(self, recall, scorer, *, candidate_limit=128):
        if type(candidate_limit) is not int or not 5 <= candidate_limit <= 128:
            raise ValueError("invalid candidate limit")
        if not callable(scorer):
            raise ValueError("scorer must be callable")
        self.base = recall
        self.scorer = scorer
        self.candidate_limit = candidate_limit

    def recall(self, query, *, max_items=5, max_chars=4000,
               max_item_chars=800, **options):
        if any(type(v) is not int or v < 1
               for v in (max_items, max_chars, max_item_chars)):
            raise ValueError("invalid output limits")
        if max_items > self.candidate_limit:
            raise ValueError("output exceeds candidate limit")
        if options.get("max_tokens") is not None or options.get("token_counter") is not None:
            raise ValueError("token budgets require canonical recall")
        candidates = self.base.recall(query, max_items=self.candidate_limit,
            max_chars=self.candidate_limit * max_item_chars,
            max_item_chars=max_item_chars, **options)
        scores = list(self.scorer(query, [item.content for item in candidates.items]))
        if len(scores) != len(candidates.items):
            raise ValueError("scorer returned wrong count")
        if any(type(s) not in (float, int) or not math.isfinite(s) for s in scores):
            raise ValueError("invalid relevance score")
        order = sorted(zip(candidates.items, scores),
                       key=lambda pair: (-pair[1], pair[0].information_id))
        selected = []
        remaining = max_chars
        for item, score in order:
            if len(selected) >= max_items or remaining == 0:
                break
            text = item.content[:min(remaining, max_item_chars)]
            reference = dict(item.excerpt_reference) if item.excerpt_reference else None
            if reference is not None:
                reference["end"] = reference["start"] + len(text)
            selected.append(replace(item, content=text,
                truncated=item.truncated or len(text) < len(item.content),
                excerpt_reference=reference,
                ranking={"policy": "canonical-rerank/1", "relevance_score": float(score),
                         "original": item.ranking},
                selection_reasons=item.selection_reasons + ("reranked_after_policy",)))
            remaining -= len(text)
        return replace(candidates, items=tuple(selected),
                       used_chars=max_chars - remaining, used_tokens=None)
