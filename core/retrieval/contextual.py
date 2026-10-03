"""Explain scope/time/status before selecting bounded canonical excerpts.

Operational mode excludes expired, out-of-scope, refuted, superseded and pending
removal candidates. Unknowns and declared conflicts remain explicit review items.
Historical mode exposes those current records with warnings, not old revisions.
"""
from collections import Counter
from contextlib import ExitStack
from copy import deepcopy
from dataclasses import asdict, dataclass, field

from core.dossiers.projects import ProjectDossiers
from core.operations.errors import OperationConflict
from core.operations.readiness import check_readiness
from core.persistence import exclusive_write
from core.retrieval.context import ContextAssembler, ContextItem
from core.routing.policy import applicability, _instant
from core.threads.storage import ThreadStorage


@dataclass(frozen=True)
class RecallItem(ContextItem):
    availability: str | None = None
    applicability: str = 'UNKNOWN'
    needs_review: bool = True
    selection_reasons: tuple[str, ...] = ()
    provenance: dict = field(default_factory=dict)
    context: dict = field(default_factory=dict)
    temporal: dict = field(default_factory=dict)
    verification: dict = field(default_factory=dict)
    relations: tuple = ()
    freshness: str = 'CANONICAL_AT_READ'


@dataclass(frozen=True)
class RecallBundle:
    query: str
    mode: str
    query_scope: dict
    at: str | None
    items: tuple[RecallItem, ...]
    used_chars: int
    used_tokens: int | None
    excluded_counts: dict
    dossier_status: str | None = None
    policy_version: str = 'contextual-recall/0.1'


class ContextualRecall:
    def __init__(self, backend):
        if (backend.persistent_root.name != 'persistent' or backend.persistent_root.parent.name != 'memory'
                or backend.history_root.absolute() != (backend.persistent_root.parent / 'history').absolute()):
            raise ValueError('contextual recall requires canonical engine roots')
        self.backend = backend
        self.root = backend.persistent_root.parent.parent
        self.storage = ThreadStorage.__new__(ThreadStorage)
        self.storage.persistent_root = backend.persistent_root
        self.storage.threads_root = backend.persistent_root / 'threads'

    def recall_payload(self, query, *, max_payload_chars, max_payload_tokens=None,
                       payload_token_counter=None, prefix='', suffix='', **options):
        from core.retrieval.payload import render, validate_limits
        limits = dict(max_payload_chars=max_payload_chars, max_payload_tokens=max_payload_tokens,
                      payload_token_counter=payload_token_counter, prefix=prefix, suffix=suffix)
        validate_limits(**limits)
        return render(self.recall(query, **options), **limits)

    def recall(self, query, *, query_scope=None, at=None, mode='operational', project_id=None,
               max_items=5, max_chars=4000, max_item_chars=1000,
               max_tokens=None, token_counter=None, include_structured_content=False, availability=None):
        if mode not in {'operational', 'historical'}:
            raise ValueError('unknown recall mode')
        if availability is not None and availability not in {'HIGH', 'INTERMEDIATE', 'LOW'}:
            raise ValueError('unknown availability filter')
        if query_scope is not None and not isinstance(query_scope, dict):
            raise ValueError('query_scope must be an object')
        if at is not None:
            if not isinstance(at, str):
                raise ValueError('at must be an explicit timestamp')
            _instant(at)  # Timezone is mandatory; no implicit wall-clock default.
        scope = deepcopy(query_scope) if query_scope is not None else {}
        excluded = Counter()
        selected = {}
        # Snapshot cooperating canonical writers. Existing lock inodes may be
        # created, but no memory, journal, dossier or receipt is modified.
        with ExitStack() as locks:
            locks.enter_context(exclusive_write(self.backend.persistent_root))
            if self.storage.threads_root.is_dir():
                locks.enter_context(exclusive_write(self.storage.threads_root))
            readiness = check_readiness(self.root)
            if not readiness['ready']:
                raise OperationConflict('readiness blocks contextual recall; recover or review the engine first')
            project_ids = None
            dossier_status = None
            if project_id is not None:
                project = self.storage.get(project_id)
                if project is None:
                    raise OperationConflict('recall project does not exist')
                project_ids = self.storage._concerns(project)
                dossier = ProjectDossiers(self.backend, self.storage, self.backend.persistent_root.parent / 'dossiers')
                dossier_status = dossier.status(project_id)['status']

            def accept(memory):
                if availability is not None and memory.metadata.get('availability') != availability:
                    excluded['OTHER_AVAILABILITY'] += 1
                    return False
                if project_ids is not None and memory.information_id not in project_ids:
                    excluded['OUTSIDE_PROJECT'] += 1
                    return False
                current = self.backend.get(memory.information_id)
                if current != memory:
                    excluded['STALE_CANDIDATE'] += 1
                    return False
                epistemic = memory.metadata.get('epistemic_status')
                reasons = ['canonical_source', 'lexical_v1_candidate']
                try:
                    applies = applicability(memory, scope, at=at, unresolved_conflict=epistemic == 'CONFLICTED')
                except (TypeError, AttributeError, ValueError):
                    applies = 'UNKNOWN'
                    reasons.append('invalid_context_or_temporal')
                receipt_path = self.backend.pending_delete_root / (memory.information_id + '.json')
                pending = (receipt_path.exists() and
                           self.backend._load_delete_request(receipt_path, memory.information_id)['status'] == 'PENDING_DELETE')
                refusal = (applies if applies in {'EXPIRED', 'OUT_OF_SCOPE'} else
                           epistemic if epistemic in {'REFUTED', 'SUPERSEDED'} else
                           'PENDING_DELETE' if pending else None)
                if mode == 'operational' and refusal is not None:
                    excluded[refusal] += 1
                    return False
                reasons.append('applicability_' + applies.lower())
                reasons.append('epistemic_' + (epistemic.lower() if isinstance(epistemic, str) else 'unspecified'))
                if pending:
                    reasons.append('pending_deletion')
                if memory.metadata.get('recheck_required'):
                    reasons.append('explicit_recheck_required')
                if mode == 'historical':
                    reasons.append('historical_mode')
                selected[memory.information_id] = (deepcopy(memory), applies,
                    applies != 'MATCH' or epistemic != 'CONFIRMED' or bool(pending)
                    or bool(memory.metadata.get('recheck_required')), tuple(reasons))
                return True

            bundle = ContextAssembler(self.backend).assemble(
                query, max_items=max_items, max_chars=max_chars, max_item_chars=max_item_chars,
                max_tokens=max_tokens, token_counter=token_counter, ranking='lexical_v1',
                include_structured_content=include_structured_content, candidate_filter=accept)
            items = []
            for item in bundle.items:
                memory, applies, review, reasons = selected[item.information_id]
                items.append(RecallItem(**asdict(item), availability=memory.metadata.get('availability'),
                                        applicability=applies, needs_review=review,
                                        selection_reasons=reasons, provenance=memory.provenance,
                                        context=deepcopy(memory.metadata.get('context', {})), temporal=memory.temporal,
                                        verification=memory.verification, relations=tuple(memory.relations)))
            return RecallBundle(query, mode, scope, at, tuple(items), bundle.used_chars,
                                bundle.used_tokens, dict(sorted(excluded.items())), dossier_status)
