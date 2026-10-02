"""Resume canonical work, dispatch explicit deadlines, reconcile derived views.

The child journals and source manifests are the durable progress record. A
restart repeats the pass without replaying completed canonical effects. No new
parent journal, cron, wall clock, human-note ingestion or deletion policy.
"""
from contextlib import ExitStack
from copy import deepcopy
from pathlib import Path

from core.backend.errors import BackendError
from core.dossiers.projects import ProjectDossiers, DossierConflict
from core.dossiers.reconciliation import DossierReconciler
from core.events.errors import EventRepositoryError
from core.indexing.catalogue import InformationCatalogue
from core.lifecycle.journal import timestamp
from core.lifecycle.service import LifecycleTriggers
from core.operations.errors import OperationConflict, OperationRepositoryError
from core.operations.readiness import check_readiness, recover_all
from core.operations.read_phase import settled_read_phase
from core.persistence import exclusive_write
from core.threads.storage import ThreadStorageError
from core.threads.manager import ThreadError

ERRORS = (OSError, ValueError, TypeError, KeyError, BackendError, DossierConflict,
          EventRepositoryError, OperationRepositoryError, ThreadStorageError, ThreadError)


class MaintenancePass:
    def __init__(self, root):
        self.root = Path(root)
        self.catalogue = InformationCatalogue(self.root)
        self.backend = self.catalogue.backend
        self.storage = self.catalogue.storage
        self.lifecycle = LifecycleTriggers(self.backend)
        self.dossiers = DossierReconciler(ProjectDossiers(
            self.backend, self.storage, self.root / 'memory/dossiers'))

    @staticmethod
    def _checkpoint(stage):
        """Fault-injection boundary after a durable child step."""

    def _deadlines(self, at):
        instant = timestamp(at)
        records = [self.lifecycle.journal.read(identity) for identity in self.lifecycle.journal.ids()]
        scheduled = [r for r in records if r['status'] == 'SCHEDULED']
        scheduled.sort(key=lambda r: (timestamp(r['command']['due_at']), r['trigger_id']))
        due = [dict(trigger_id=r['trigger_id'], **{key: r['command'][key]
                    for key in ('target_id', 'revision', 'kind', 'due_at')})
               for r in scheduled if timestamp(r['command']['due_at']) <= instant]
        future = [r for r in scheduled if timestamp(r['command']['due_at']) > instant]
        return dict(due=due, future_count=len(future),
                    next_due_at=future[0]['command']['due_at'] if future else None)

    def inspect(self, *, at):
        """No writes, not even repository/lock initialization; stopped-copy view."""
        timestamp(at)
        readiness = check_readiness(self.root)
        report = dict(status='BLOCKED', at=at, readiness=readiness,
                      deadlines=None, dossiers=None, catalogue=None)
        if not readiness['ready']:
            return report
        try:
            report['deadlines'] = self._deadlines(at)
            report['dossiers'] = self.dossiers.inspect()
            report['catalogue'] = self.catalogue.status()
            if report['dossiers']['status'] != 'BLOCKED':
                report['status'] = 'READY'
                report['work_pending'] = bool(report['deadlines']['due'] or
                    report['dossiers']['status'] != 'CLEAN' or report['catalogue']['status'] != 'CURRENT')
        except ERRORS as exc:
            report['error'] = dict(type=type(exc).__name__, reason=str(exc))
        return report

    def run(self, *, at, query_scope=None, limit=100):
        """One explicit pass. Limit bounds due dispatch only, not recovery/scans."""
        timestamp(at)
        if type(limit) is not int or limit < 1 or (query_scope is not None and not isinstance(query_scope, dict)):
            raise ValueError('positive limit and object query_scope required')
        scope = deepcopy(query_scope) if query_scope is not None else {}
        report = dict(status='BLOCKED', at=at, stage='readiness', recovery=None,
                      triggers={}, dossiers=None, catalogue=None, verification=None)
        try:
            state = check_readiness(self.root)
            report['readiness'] = state
            if any(not issue['resumable'] for issue in state['issues']):
                return report
            if not self.backend.persistent_root.is_dir():
                raise ValueError('existing engine Persistent directory required')
            with ExitStack() as locks:
                locks.enter_context(exclusive_write(self.backend.persistent_root))
                if self.storage.threads_root.is_dir():
                    locks.enter_context(exclusive_write(self.storage.threads_root))
                if state['ready'] and not self._deadlines(at)['due']:
                    with settled_read_phase(self.root):
                        idle = self.inspect(at=at)
                    if idle['status'] == 'READY' and not idle['work_pending']:
                        report.update(status='COMPLETED', stage='done', verification=idle,
                                      dossiers=dict(idle['dossiers'], actions=[]),
                                      catalogue=dict(idle['catalogue'], status='UNCHANGED'))
                        return report
                report['stage'] = 'recovery'
                report['recovery'] = recover_all(self.root)
                if not report['recovery']['readiness']['ready']:
                    return report
                self._checkpoint('after_recovery')
                report['stage'] = 'triggers'
                effects = self.lifecycle.run_due(at=at, query_scope=scope, limit=limit)
                report['triggers'] = {identity: dict(status=record['status'], reason=record['result']['reason'])
                                      for identity, record in effects.items()}
                self._checkpoint('after_triggers')
                with settled_read_phase(self.root):
                    report['stage'] = 'dossiers'
                    report['dossiers'] = self.dossiers.apply()
                    if report['dossiers']['status'] == 'BLOCKED':
                        return report
                    self._checkpoint('after_dossiers')
                    report['stage'] = 'catalogue'
                    report['catalogue'] = self.catalogue.rebuild()
                    self._checkpoint('after_catalogue')
                report['stage'] = 'verification'
                with settled_read_phase(self.root):
                    report['verification'] = self.inspect(at=at)
                final = report['verification']
                if (final['status'] != 'READY' or final['dossiers']['status'] != 'CLEAN'
                        or final['catalogue']['status'] != 'CURRENT'):
                    raise OperationConflict('maintenance final verification failed')
                report['status'] = 'PARTIAL' if final['deadlines']['due'] else 'COMPLETED'
                report['stage'] = 'done'
        except ERRORS as exc:
            report['error'] = dict(type=type(exc).__name__, reason=str(exc))
        return report
