# ==========================================================
# Projet      : Eidolon Memory Engine
# Organisation: Eidolon Core Technologies (ECT)
# Fichier     : core/retrieval/indexed.py
# Description : Resolve bounded index identities against canonical Information.
# Standard    : Eidolon Presentation Standard v1
# ==========================================================
"""Internal search view for ContextualRecall, used under its canonical locks.

The caller selects a trusted, already access-scoped index and backend. This
view is not a user authorization boundary. Index scores never establish truth
or sufficient relevance; no implicit fallback or abstention threshold is used.
"""
from copy import deepcopy
import math
import re

from core.backend.models import SearchResult
from core.indexing.port import IndexHit


class CanonicalIndexCandidates:
    """One candidate snapshot per recall; do not reuse across recall calls."""

    def __init__(self, backend, index, limit, excluded):
        self.backend = backend
        self.index = index
        self.limit = limit
        self.excluded = excluded
        self._results = None

    def search(self, query, options):
        if self._results is None:
            hits = self.index.query(query, limit=self.limit)
            if not isinstance(hits, list) or len(hits) > self.limit:
                raise ValueError('invalid index candidate batch')
            # Validate the entire bounded batch before adopting any candidate.
            for hit in hits:
                if (not isinstance(hit, IndexHit)
                        or not isinstance(hit.information_id, str)
                        or not re.fullmatch(r'[A-Za-z0-9._-]+', hit.information_id)
                        or hit.information_id in {'.', '..'}
                        or type(hit.score) not in (int, float)
                        or not math.isfinite(hit.score)
                        or not isinstance(hit.ranking, dict)
                        or type(hit.ranking.get('revision')) is not int
                        or hit.ranking['revision'] < 1):
                    raise ValueError('invalid index candidate identity, score or revision')
                if 'passage' in hit.ranking:
                    from core.retrieval.archive_chunks import validate_reference
                    validate_reference(hit.ranking['passage'])
            results = []
            seen = set()
            for hit in hits:
                if hit.information_id in seen:
                    continue
                memory = self.backend.get(hit.information_id)
                if memory is None:
                    self.excluded['INDEX_MISSING_CANONICAL'] += 1
                    continue
                if memory.revision != hit.ranking['revision']:
                    self.excluded['INDEX_REVISION_MISMATCH'] += 1
                    continue
                from core.sources.chatgpt_import import is_conversation_archive
                from core.retrieval.archive_chunks import validate_canonical_reference
                if 'passage' in hit.ranking:
                    try:
                        if not is_conversation_archive(memory):
                            raise ValueError('index passage requires a conversation archive')
                        validate_canonical_reference(memory.content, hit.ranking['passage'])
                    except (ValueError, TypeError):
                        self.excluded['INDEX_PASSAGE_UNRESOLVED'] += 1
                        continue
                elif is_conversation_archive(memory):
                    # A semantic archive identity alone cannot locate its evidence.
                    # Do not silently substitute a lexical passage from that archive.
                    self.excluded['INDEX_PASSAGE_MISSING'] += 1
                    continue
                # Never take content, provenance or applicability from the index.
                ranking = {'policy': 'canonical-index-candidates/1',
                           'candidate_score': hit.score,
                           'canonical_revision': memory.revision,
                           'index': {key: deepcopy(hit.ranking[key]) for key in
                                     ('policy', 'embedding_id', 'revision',
                                      'source_digest', 'index_freshness')
                                     if key in hit.ranking}}
                metadata = {'ranking': ranking}
                if 'passage' in hit.ranking:
                    metadata['index_passage'] = deepcopy(hit.ranking['passage'])
                results.append(SearchResult(memory, hit.score, metadata))
                seen.add(hit.information_id)
            self._results = results
        offset, limit = options['offset'], options['limit']
        return self._results[offset:offset + limit]
