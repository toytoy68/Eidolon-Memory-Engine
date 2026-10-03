"""Durable routing intentions and compact terminal results; no implicit execution."""
from contextlib import contextmanager
from contextvars import ContextVar
from hashlib import sha256
import json
from pathlib import Path
import re

from core.operations.errors import OperationConflict
from core.persistence import atomic_write_text, has_symlink_component
from core.storage_format import decode_json_value

FAMILY = 'routing-execution-v1'
_active = ContextVar('routing_execution_owner', default=None)


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def digest(value):
    return sha256(canonical(value).encode()).hexdigest()


class ExecutionJournal:
    def __init__(self, history_root):
        self.history_root = Path(history_root)
        self.root = self.history_root / 'operations' / FAMILY

    def path(self, identity):
        if not isinstance(identity, str) or not re.fullmatch(r'[A-Za-z0-9._-]+', identity):
            raise OperationConflict('invalid routing intent identity')
        path = self.root / (identity + '.json')
        if has_symlink_component(path):
            raise OperationConflict('unsafe routing journal path')
        return path

    def ids(self):
        if has_symlink_component(self.root) or (self.root.exists() and not self.root.is_dir()):
            raise OperationConflict('unsafe routing journal')
        return [path.stem for path in sorted(self.root.glob('*.json'))]

    def read(self, identity):
        path = self.path(identity)
        if not path.exists():
            return None
        try:
            record = decode_json_value(path.read_text(encoding='utf-8'))
            common = {'format_version', 'intent_id', 'status', 'fingerprint'}
            if (not isinstance(record, dict) or type(record.get('format_version')) is not int
                    or record['format_version'] not in {1, 2, 3, 4} or record.get('intent_id') != identity
                    or not isinstance(record.get('fingerprint'), str)
                    or not re.fullmatch('[0-9a-f]{64}', record['fingerprint'])):
                raise ValueError('invalid routing identity/version')
            if record.get('status') == 'APPLYING':
                if set(record) != common | {'command'} or digest(record['command']) != record['fingerprint']:
                    raise ValueError('invalid routing command fingerprint')
                command = record['command']
                if set(command) != {'prepared', 'actor', 'timestamp'}:
                    raise ValueError('invalid routing command')
                prepared = command['prepared']
                fields = {'format_version', 'memory', 'context', 'policy', 'project_before', 'information_before'}
                if record['format_version'] == 3:
                    fields.add('project_create')
                if (set(prepared) != fields
                        or type(prepared['format_version']) is not int
                        or prepared['format_version'] != record['format_version']):
                    raise ValueError('invalid routing plan')
                # These references must be readable even if the semantic plan
                # is blocked. Recovery performs full policy/snapshot validation.
                reserved_targets(record)
            elif record.get('status') == 'COMMITTED':
                if set(record) != common | {'result'}:
                    raise ValueError('invalid routing receipt')
                result = record['result']
                keys = {'information', 'project', 'projection_digest', 'deferred'}
                if record['format_version'] in {2, 3}:
                    keys.add('lifecycle')
                if set(result) != keys:
                    raise ValueError('invalid routing result')
                for key in ('information', 'project'):
                    target = result[key]
                    if (set(target) != {'id', 'revision'} or not isinstance(target['id'], str)
                            or not re.fullmatch(r'[A-Za-z0-9._-]+', target['id'])
                            or type(target['revision']) is not int or target['revision'] < 1):
                        raise ValueError('invalid routing result target')
                if (result['deferred'] != (['availability'] if record['format_version'] in {1, 4} else [])
                        or not isinstance(result['projection_digest'], str)
                        or not re.fullmatch('[0-9a-f]{64}', result['projection_digest'])):
                    raise ValueError('invalid routing projection result')
                if record['format_version'] in {2, 3}:
                    lifecycle = result['lifecycle']
                    expected_trigger = 'routing-' + sha256(identity.encode()).hexdigest() + '-trigger'
                    if (set(lifecycle) != {'availability', 'trigger_id'}
                            or lifecycle['availability'] not in {'HIGH', 'INTERMEDIATE', 'LOW'}
                            or lifecycle['trigger_id'] not in {None, expected_trigger}):
                        raise ValueError('invalid routing lifecycle result')
            else:
                raise ValueError('unknown routing state')
            return record
        except (OSError, ValueError, TypeError, KeyError, AttributeError) as exc:
            raise OperationConflict('unreadable routing intention or receipt') from exc

    def save(self, record):
        atomic_write_text(self.path(record['intent_id']), canonical(record) + '\n')


@contextmanager
def execution_owner(history_root, identity):
    token = _active.set((str(Path(history_root).resolve()), identity))
    try:
        yield
    finally:
        _active.reset(token)


def owned_execution(history_root):
    active = _active.get()
    return active[1] if active and active[0] == str(Path(history_root).resolve()) else None


def reserved_targets(record):
    prepared = record['command']['prepared']
    memory = prepared['memory']
    project = prepared['policy']['dossier_subject']
    if not isinstance(project, dict) or project.get('kind') != 'project':
        raise ValueError('routing intention needs a project')
    identities = {memory['information_id']}
    for relation in memory['relations']:
        identities.add(relation.get('target_id') if relation.get('target_id') is not None else relation.get('target'))
    if any(not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9._-]+', value)
           for value in [project['id'], *identities]):
        raise ValueError('invalid routing reservation')
    return identities, project['id']


def require_available(history_root, *, information_id=None, thread_id=None):
    journal = ExecutionJournal(history_root)
    for identity in journal.ids():
        record = journal.read(identity)
        if record is None or record['status'] == 'COMMITTED':
            continue
        if _active.get() == (str(Path(history_root).resolve()), identity):
            continue
        information, project = reserved_targets(record)
        if information_id in information or thread_id == project:
            raise OperationConflict('recover routing intention before mutating its targets')


def audit_executions(engine_root):
    journal = ExecutionJournal(Path(engine_root) / 'memory/history')
    report = {'records': {}, 'issues': []}
    try:
        identities = journal.ids()
    except (OSError, ValueError, OperationConflict) as exc:
        report['issues'].append({'path': 'memory/history/operations/' + FAMILY,
                                 'reason': type(exc).__name__, 'resumable': False})
        return report
    for identity in identities:
        relative = 'memory/history/operations/' + FAMILY + '/' + identity + '.json'
        try:
            record = journal.read(identity)
            report['records'][relative] = record['status']
            if record['status'] != 'COMMITTED':
                report['issues'].append({'path': relative, 'reason': record['status'], 'resumable': True})
        except (OSError, ValueError, TypeError, OperationConflict) as exc:
            report['issues'].append({'path': relative, 'reason': type(exc).__name__, 'resumable': False})
    return report
