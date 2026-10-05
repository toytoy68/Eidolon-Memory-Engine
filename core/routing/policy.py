# ==========================================================
# Projet      : Eidolon Memory Engine
# Organisation: Eidolon Core Technologies (ECT)
# Fichier     : core/routing/policy.py
# Description : Reference policy v0.1: pure plans over explicitly qualified Memory objects.
# Standard    : Eidolon Presentation Standard v1
# ==========================================================

"""Reference policy v0.1: pure plans over explicitly qualified Memory objects.

No text classification, storage, scheduling or robot actions occur here.
Source authority, epistemic status and applicability remain separate axes.
"""
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime
import hashlib
import json

from core.backend.models import Memory


NATURES = {'TECHNICAL', 'REFLECTION', 'SPATIAL_LAYOUT', 'MOBILE_PRESENCE',
           'OBSTACLE', 'ACTION_REPORT', 'PROJECT_INTENT', 'CONDITIONAL_CLAIM'}


@dataclass(frozen=True)
class TargetRevision:
    information_id: str
    revision: int


@dataclass(frozen=True)
class RoutingContext:
    query_scope: dict = field(default_factory=dict)
    at: str | None = None
    explicit_memory_request: bool = False
    navigation_active: bool = False
    tracking_task: bool = False
    significant_event: bool = False
    candidate_projects: tuple[str, ...] = ()
    selected_project: str | None = None
    existing_dossier: str | None = None
    update_target: TargetRevision | None = None
    removal_observed: bool = False
    evidence_refs: tuple[str, ...] = ()
    unresolved_conflict: bool = False
    already_stored: bool = False


@dataclass(frozen=True)
class RoutingPlan:
    source_id: str
    source_revision: int
    source_provenance: dict
    source_temporal: dict
    information_type: str | None
    epistemic_status: str | None
    nature: str | None
    horizon: str
    persistence: str
    availability: str
    dossier: str
    dossier_subject: dict | None
    applicability: str
    reasons: tuple[str, ...]
    dossier_id: str | None = None
    update_target: TargetRevision | None = None
    evidence_refs: tuple[str, ...] = ()
    after_task_availability: str | None = None
    recheck_before_reuse: bool = False
    current_obstacle: bool | None = None
    proposed_trigger: dict | None = None
    automatic_delete: bool = False
    automatic_winner: str | None = None
    contract_version: str = 'memory-policy/0.1'
    rules_version: str = 'reference/0.1'
    profile: str = 'reference_without_implicit_tracking_or_deletion'


def _instant(value):
    parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError('explicit timezone required')
    return parsed


def _scope_match(expected, actual):
    missing = False
    for key, value in expected.items():
        if key not in actual:
            missing = True
        elif isinstance(value, dict):
            if not isinstance(actual[key], dict):
                return 'OUT_OF_SCOPE'
            result = _scope_match(value, actual[key])
            if result == 'OUT_OF_SCOPE':
                return result
            missing |= result == 'UNKNOWN'
        elif actual[key] != value:
            return 'OUT_OF_SCOPE'
    return 'UNKNOWN' if missing or not expected else 'MATCH'


def applicability(memory: Memory, query_scope: dict, *, at=None, unresolved_conflict=False):
    """Declared bounds plus exact context; absence never implies universality."""
    bounds = [memory.temporal.get(key) for key in ('valid_from', 'valid_until')]
    if any(bounds):
        if at is None:
            return 'UNKNOWN'
        try:
            instant = _instant(at)
            start, end = (_instant(value) if value else None for value in bounds)
            if start and end and start > end:
                return 'UNKNOWN'
            if end and instant > end:
                return 'EXPIRED'
            if start and instant < start:
                return 'OUT_OF_SCOPE'
        except (ValueError, TypeError, AttributeError):
            return 'UNKNOWN'
    scope = memory.metadata.get('context', {}).get('scope', {})
    match = _scope_match(scope, query_scope)
    if match == 'MATCH' and unresolved_conflict:
        return 'UNRESOLVED'
    return match


def plan(memory: Memory, context: RoutingContext) -> RoutingPlan:
    """Explain a proposal. Consumers must resolve dossiers and execute explicitly."""
    labels = memory.metadata.get('qualification', {})
    nature = labels.get('nature')
    declared_horizon = labels.get('horizon', 'UNKNOWN')
    horizon = declared_horizon
    association = memory.metadata.get('context', {})
    project = context.selected_project or association.get('project_id')
    subject = ({'kind': 'project', 'id': project} if project else
               {'kind': 'topic', 'id': association['topic_id']} if association.get('topic_id') else
               {'kind': 'place', 'id': association['place_id']} if association.get('place_id') else None)
    reasons = ['epistemic_status_preserved_independently_of_source_role']
    persistence, availability, dossier = 'REVIEW', 'INTERMEDIATE', 'NONE'
    after_task = None
    recheck = False
    current_obstacle = None
    proposed_trigger = None
    target = None
    evidence = ()
    qualified = (labels.get('version') == '0.1' and nature in NATURES
                 and bool(labels.get('qualified_by')))
    if context.removal_observed:
        if (qualified and nature == 'OBSTACLE'
                and context.update_target == TargetRevision(memory.information_id, memory.revision)
                and context.evidence_refs
                and all(isinstance(ref, str) and ref.strip() for ref in context.evidence_refs)):
            persistence, target, evidence = 'UPDATE', context.update_target, tuple(context.evidence_refs)
            current_obstacle = False
            reasons.append('observed_removal_updates_known_revision_with_evidence_keeps_history')
        else:
            reasons.append('removal_needs_qualified_obstacle_matching_revision_and_evidence_refs')
    elif not qualified:
        reasons.append('explicit_qualification_required_no_inference_from_text')
    elif nature == 'REFLECTION' and not context.explicit_memory_request and project is None:
        persistence, availability = 'NONE', 'HIGH'
        reasons.append('general_reflection_without_memory_request')
    elif nature == 'MOBILE_PRESENCE' and not (
        context.tracking_task or context.significant_event or context.explicit_memory_request
    ):
        persistence, availability, horizon = 'NONE', 'HIGH', 'IMMEDIATE'
        reasons.append('transient_presence_without_tracking_no_future_position_inferred')
    else:
        persistence = 'STORE'
        if nature == 'SPATIAL_LAYOUT':
            horizon = 'LONG_TERM' if declared_horizon == 'UNKNOWN' else declared_horizon
            availability = 'HIGH' if context.navigation_active else 'LOW'
            reasons.append('layout_candidate_not_automatically_confirmed')
            if not association.get('place_id'):
                persistence = 'REVIEW'
                reasons.append('layout_requires_declared_place')
        elif nature in {'OBSTACLE', 'MOBILE_PRESENCE', 'ACTION_REPORT'}:
            availability, after_task = 'HIGH', 'INTERMEDIATE'
            if nature == 'OBSTACLE':
                recheck = True
                reasons.append('obstacle_requires_recheck_bypass_is_not_removal')
            elif nature == 'MOBILE_PRESENCE':
                reasons.append('task_relevant_observation_preserves_observation_time')
            else:
                reasons.append('action_report_does_not_change_obstacle_state')
        else:
            availability = 'LOW' if declared_horizon == 'LONG_TERM' else 'INTERMEDIATE'
            reasons.append('qualified_information_or_explicit_memory_request')
        if persistence == 'STORE' and context.update_target is not None:
            persistence, target = 'UPDATE', context.update_target
            reasons.append('explicit_target_and_revision_for_update')
        if subject is not None:
            dossier = 'LINK' if context.existing_dossier or context.tracking_task else 'CREATE_OR_LINK'
            reasons.append('resolve_existing_dossier_before_creating_projection')
        if persistence in {'STORE', 'UPDATE'} and memory.temporal.get('resume_at') is not None:
            try:
                _instant(memory.temporal['resume_at'])
            except (ValueError, TypeError, AttributeError):
                persistence, target = 'REVIEW', None
                reasons.append('resume_at_requires_valid_explicit_timezone')
            else:
                availability = 'INTERMEDIATE'
                payload = json.dumps([memory.information_id, memory.revision, memory.temporal['resume_at']],
                                     ensure_ascii=False, separators=(',', ':'))
                proposed_trigger = {'kind': 'REACTIVATE', 'at': memory.temporal['resume_at'],
                                    'trigger_id': 'reactivate-' + hashlib.sha256(payload.encode()).hexdigest()}
                reasons.append('scheduled_reactivation_proposal_requires_T046_executor')
    if context.candidate_projects and (
        project is None or project not in context.candidate_projects
    ):
        dossier, subject = 'REVIEW', None
        reasons.append('ambiguous_project_no_automatic_merge')
    if context.already_stored and persistence == 'STORE':
        persistence = 'NONE'
        reasons.append('existing_memory_no_duplicate_store')
    if persistence not in {'STORE', 'UPDATE'}:
        proposed_trigger = None
        reasons = [reason for reason in reasons
                   if reason not in {'scheduled_reactivation_proposal_requires_T046_executor',
                                     'explicit_target_and_revision_for_update'}]
    applies = applicability(memory, context.query_scope, at=context.at,
                            unresolved_conflict=context.unresolved_conflict)
    reasons.append('applicability_' + applies.lower())
    if applies == 'EXPIRED':
        availability = 'LOW'
        reasons.append('expired_applicability_does_not_refute_or_delete_history')
    if applies == 'UNRESOLVED':
        reasons.append('same_context_conflict_requires_evidence_no_automatic_winner')
    return RoutingPlan(
        source_id=memory.information_id, source_revision=memory.revision,
        source_provenance=deepcopy(memory.provenance), source_temporal=deepcopy(memory.temporal),
        information_type=memory.metadata.get('type'),
        epistemic_status=memory.metadata.get('epistemic_status'), nature=nature, horizon=horizon,
        persistence=persistence, availability=availability, dossier=dossier,
        dossier_subject=deepcopy(subject), applicability=applies, reasons=tuple(reasons),
        dossier_id=context.existing_dossier if dossier == 'LINK' else None,
        update_target=target, evidence_refs=evidence, after_task_availability=after_task,
        recheck_before_reuse=recheck, current_obstacle=current_obstacle,
        proposed_trigger=proposed_trigger,
    )
