# ==========================================================
# Projet      : Eidolon Memory Engine
# Organisation: Eidolon Core Technologies (ECT)
# Fichier     : core/dossiers/reconciliation.py
# Description : Reconcile managed project views from current canonical files.
# Standard    : Eidolon Presentation Standard v1
# ==========================================================

"""Reconcile managed project views from current canonical files.

No durable queue is necessary: missing/stale generated regions are the work
remaining after an interruption. Inspection writes nothing. Apply rechecks all
sources under cooperative locks and publishes each dossier atomically.
"""
from contextlib import ExitStack
from hashlib import sha256

from core.backend.errors import BackendError
from core.dossiers.projects import BEGIN, END, DossierConflict
from core.operations.errors import OperationRepositoryError
from core.operations.readiness import check_readiness
from core.operations.read_phase import settled_read_phase
from core.persistence import exclusive_write, has_symlink_component
from core.threads.storage import ThreadStorageError


READ_ERRORS = (DossierConflict, BackendError, ThreadStorageError,
               OperationRepositoryError, OSError, ValueError, TypeError)


class DossierReconciler:
    def __init__(self, dossiers):
        self.dossiers = dossiers
        persistent = dossiers.backend.persistent_root
        if (persistent.name != 'persistent' or persistent.parent.name != 'memory'
                or dossiers.backend.history_root.absolute() != (persistent.parent / 'history').absolute()):
            raise DossierConflict('reconciliation requires canonical engine roots')
        self.engine_root = persistent.parent.parent

    def inspect(self):
        """Read-only point-in-time report; use a stopped copy for stability."""
        dossiers = self.dossiers
        report = {'status': 'CLEAN', 'items': [], 'issues': [],
                  'scope': 'managed_generated_regions_only', 'manifest_version': 1}
        try:
            for root in (dossiers.root, dossiers.storage.threads_root):
                if has_symlink_component(root) or (root.exists() and not root.is_dir()):
                    raise DossierConflict('invalid dossier or Thread directory')
            readiness = check_readiness(self.engine_root)
            if not readiness['ready']:
                return dict(report, status='BLOCKED', issues=readiness['issues'])
            thread_ids = {path.stem for path in dossiers.storage.threads_root.glob('*.md')}
            view_ids = {path.stem for path in dossiers.root.glob('*.md')}
            for thread_id in sorted(thread_ids | view_ids):
                item = {'thread_id': thread_id}
                try:
                    path = dossiers._path(thread_id)
                    previous = dossiers._read_text(path) if path.exists() else None
                    # An unrelated Markdown file is never adopted or overwritten.
                    if previous is not None and BEGIN not in previous and END not in previous:
                        if thread_id in thread_ids:
                            raise DossierConflict('unmanaged file occupies a project dossier path')
                        report['items'].append(dict(item, status='UNMANAGED'))
                        continue
                    source = dossiers._source(thread_id)
                    thread, memories, missing, digest = source
                    dependencies = []
                    for kind, identity, obj, source_path in [
                        ('thread', thread_id, thread, dossiers.storage._path(thread_id)),
                        *(('information', memory.information_id, memory,
                           dossiers.backend._path(memory.information_id)) for memory in memories),
                        *(('information', identity, None, dossiers.backend._path(identity)) for identity in missing),
                    ]:
                        dependencies.append({'kind': kind, 'id': identity,
                                             'revision': obj.revision if obj is not None else None,
                                             'sha256': sha256(source_path.read_bytes()).hexdigest() if obj is not None else None})
                    if previous is None:
                        state = 'MISSING'
                    else:
                        _, generated, _ = dossiers._parts(previous)
                        state = ('CURRENT' if generated == dossiers._generated(thread_id, source)
                                 else 'ORPHANED' if thread is None else 'STALE')
                    item.update(status=state, source_digest=digest, dependencies=dependencies)
                except READ_ERRORS as exc:
                    item.update(status='BLOCKED', reason=str(exc))
                report['items'].append(item)
        except READ_ERRORS as exc:
            report['issues'].append({'reason': str(exc)})
        if report['issues'] or any(item['status'] == 'BLOCKED' for item in report['items']):
            report['status'] = 'BLOCKED'
        elif any(item['status'] in {'MISSING', 'STALE', 'ORPHANED'} for item in report['items']):
            report['status'] = 'DRIFT'
        return report

    def apply(self, *, limit=None):
        """Recompute work; rerunning converges without replaying canonical writes.

        Failures during publication propagate. Earlier atomic publications stay
        valid; inspection discovers the remaining work on the next invocation.
        """
        if limit is not None and (type(limit) is not int or not 1 <= limit <= 100):
            raise ValueError('dossier limit must be an integer from 1 to 100')
        dossiers = self.dossiers
        with ExitStack() as locks:
            locks.enter_context(exclusive_write(dossiers.backend.persistent_root))
            if dossiers.storage.threads_root.is_dir():
                locks.enter_context(exclusive_write(dossiers.storage.threads_root))
            if dossiers.root.exists():
                locks.enter_context(exclusive_write(dossiers.root))
            locks.enter_context(settled_read_phase(self.engine_root))
            report = self.inspect()
            if report['status'] != 'DRIFT':
                return dict(report, actions=[])
            if not dossiers.root.exists():
                dossiers.root.mkdir(parents=True)
                locks.enter_context(exclusive_write(dossiers.root))
                # Recheck after acquiring the output lock, before publishing.
                report = self.inspect()
                if report['status'] == 'BLOCKED':
                    return dict(report, actions=[])
            actions = []
            for item in report['items']:
                if item['status'] in {'MISSING', 'STALE', 'ORPHANED'}:
                    if limit is not None and len(actions) >= limit:
                        break
                    result = dossiers.rebuild(item['thread_id'])
                    actions.append(dict(result, thread_id=item['thread_id']))
            final = self.inspect()
            if limit is not None:
                final['remaining_count'] = sum(item['status'] in {'MISSING', 'STALE', 'ORPHANED'}
                                               for item in final['items'])
                if final['status'] == 'DRIFT':
                    final['status'] = 'PARTIAL'
            if final['status'] == 'CLEAN' and actions:
                final['status'] = 'RECONCILED'
            return dict(final, actions=actions)
