"""Read-only client outcomes; no durable decisions or implicit execution.

An outcome explains the next explicit step. It neither asserts readiness nor
reserves a target, and cannot be supplied as an executable prepared plan.
"""
from dataclasses import asdict

from core.backend.filesystem import FilesystemBackend
from core.routing.execution_journal import canonical
from core.routing.policy import plan
from core.storage_format import decode_json_value


def assess(memory, context):
    FilesystemBackend._serialize_checked(memory)
    policy = decode_json_value(canonical(asdict(plan(memory, context))))
    reasons = []
    if policy['persistence'] == 'REVIEW' or policy['dossier'] == 'REVIEW':
        reasons.extend(policy['reasons'])
    if context.removal_observed:
        reasons.append('removal_evidence_requires_review')
    if policy['applicability'] == 'UNRESOLVED':
        reasons.append('same_context_conflict_requires_evidence_no_automatic_winner')
    if (policy['persistence'] == 'NONE'
            and policy['dossier'] in {'LINK', 'CREATE_OR_LINK'}):
        subject = policy['dossier_subject']
        explicit_link = (context.already_stored is True and isinstance(subject, dict)
                         and subject.get('kind') == 'project' and context.existing_dossier == subject['id'])
        if not explicit_link:
            reasons.append('association_requires_explicit_command')
    if reasons:
        status, next_step = 'REVIEW_REQUIRED', 'RESOLVE_REVIEW'
    elif policy['persistence'] == 'NONE':
        if policy['dossier'] in {'LINK', 'CREATE_OR_LINK'}:
            status, next_step = 'PREVIEW_REQUIRED', 'PREVIEW_LINK_EXISTING'
        else:
            status, next_step = 'NO_ACTION', 'DO_NOT_PERSIST'
    else:
        subject = policy['dossier_subject']
        if (not isinstance(subject, dict) or subject.get('kind') != 'project'
                or policy['dossier'] not in {'LINK', 'CREATE_OR_LINK'}):
            status, next_step = 'CAPABILITY_REQUIRED', 'UNSUPPORTED_ROUTE'
        else:
            status = 'PREVIEW_REQUIRED'
            next_step = ('PREVIEW_EXISTING_PROJECT' if context.existing_dossier is not None
                         else 'RESOLVE_PROJECT')
    return {'contract_version': 'routing-outcome/1', 'status': status,
            'next_step': next_step, 'policy': policy,
            'review_reasons': list(dict.fromkeys(reasons)),
            'writes_performed': False, 'execution_validated': False}
