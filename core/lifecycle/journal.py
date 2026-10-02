"""Content-free lifecycle intentions. SCHEDULED is waiting, not failed recovery."""
from pathlib import Path
import re

from core.operations.errors import OperationConflict
from core.persistence import atomic_write_text, has_symlink_component
from core.routing.execution_journal import canonical, digest
from core.routing.policy import _instant
from core.storage_format import decode_json_value

FAMILY = 'lifecycle-trigger-v1'
TERMINAL = {'COMPLETED', 'CANCELLED', 'STALE', 'SKIPPED'}


def identity(value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9._-]+', value):
        raise ValueError('invalid lifecycle identity')


def timestamp(value):
    if not isinstance(value, str):
        raise ValueError('explicit timezone-aware timestamp required')
    return _instant(value)


class TriggerJournal:
    def __init__(self, history_root):
        self.root = Path(history_root) / 'operations' / FAMILY

    def path(self, trigger_id):
        identity(trigger_id)
        path = self.root / (trigger_id + '.json')
        if has_symlink_component(path):
            raise OperationConflict('unsafe lifecycle journal path')
        return path

    def ids(self):
        if has_symlink_component(self.root) or (self.root.exists() and not self.root.is_dir()):
            raise OperationConflict('unsafe lifecycle journal directory')
        return [path.stem for path in sorted(self.root.glob('*.json'))]

    @staticmethod
    def validate(record, trigger_id):
        if (not isinstance(record, dict) or set(record) != {
                'format_version', 'trigger_id', 'status', 'command', 'fingerprint',
                'source_sha256', 'run', 'result'}
                or type(record['format_version']) is not int or record['format_version'] != 1
                or record['trigger_id'] != trigger_id):
            raise ValueError('unsupported lifecycle record')
        command = record['command']
        if (not isinstance(command, dict) or set(command) != {
                'target_id', 'revision', 'kind', 'due_at', 'actor', 'created_at'}
                or record['fingerprint'] != digest(command)
                or type(command['revision']) is not int or command['revision'] < 1
                or command['kind'] not in {'REACTIVATE', 'RECHECK'}
                or not isinstance(command['actor'], str) or not command['actor'].strip()
                or not isinstance(record['source_sha256'], str)
                or not re.fullmatch('[0-9a-f]{64}', record['source_sha256'])):
            raise ValueError('invalid lifecycle command')
        identity(command['target_id'])
        timestamp(command['due_at'])
        timestamp(command['created_at'])
        if record['status'] not in {'SCHEDULED', 'APPLYING'} | TERMINAL:
            raise ValueError('invalid lifecycle status')
        run = record['run']
        if run is not None:
            if (not isinstance(run, dict) or set(run) != {'at', 'query_scope', 'effect', 'fingerprint'}
                    or not isinstance(run['query_scope'], dict) or run['effect'] not in {'HIGH', 'RECHECK'}
                    or not isinstance(run['fingerprint'], str)
                    or not re.fullmatch('[0-9a-f]{64}', run['fingerprint'])):
                raise ValueError('invalid lifecycle execution')
            if timestamp(run['at']) < timestamp(command['due_at']):
                raise ValueError('execution precedes deadline')
        if record['status'] == 'SCHEDULED' and run is not None:
            raise ValueError('scheduled trigger already has an execution')
        if record['status'] in {'APPLYING', 'COMPLETED'} and run is None:
            raise ValueError('missing lifecycle execution')
        result = record['result']
        if record['status'] in TERMINAL:
            if (not isinstance(result, dict) or set(result) != {'at', 'actor', 'reason', 'information'}
                    or any(not isinstance(result[key], str) or not result[key] for key in ('actor', 'reason'))):
                raise ValueError('invalid lifecycle result')
            timestamp(result['at'])
            info = result['information']
            if record['status'] == 'COMPLETED':
                if (not isinstance(info, dict) or set(info) != {
                        'information_id', 'previous_revision', 'revision', 'event_id'}
                        or info['information_id'] != command['target_id']
                        or type(info['previous_revision']) is not int or info['previous_revision'] != command['revision']
                        or type(info['revision']) is not int or info['revision'] != command['revision'] + 1):
                    raise ValueError('invalid lifecycle acknowledgement')
                identity(info['event_id'])
            elif info is not None:
                raise ValueError('unexecuted trigger has a write result')
        elif result is not None:
            raise ValueError('nonterminal trigger has a result')

    def read(self, trigger_id):
        path = self.path(trigger_id)
        if not path.exists():
            return None
        try:
            record = decode_json_value(path.read_text(encoding='utf-8'))
            self.validate(record, trigger_id)
            return record
        except (OSError, ValueError, TypeError, KeyError, AttributeError) as exc:
            raise OperationConflict('invalid lifecycle journal') from exc

    def save(self, record):
        self.validate(record, record['trigger_id'])
        atomic_write_text(self.path(record['trigger_id']), canonical(record) + '\n')


def audit_triggers(engine_root):
    journal = TriggerJournal(Path(engine_root) / 'memory/history')
    report = {'records': {}, 'issues': []}
    try:
        identities = journal.ids()
    except (OSError, ValueError, OperationConflict) as exc:
        report['issues'].append({'path': 'memory/history/operations/' + FAMILY,
                                 'reason': type(exc).__name__, 'resumable': False})
        return report
    for trigger_id in identities:
        relative = 'memory/history/operations/' + FAMILY + '/' + trigger_id + '.json'
        try:
            record = journal.read(trigger_id)
            report['records'][relative] = record['status']
            if record['status'] == 'APPLYING':
                report['issues'].append({'path': relative, 'reason': 'APPLYING', 'resumable': True})
        except (OSError, ValueError, TypeError, OperationConflict) as exc:
            report['issues'].append({'path': relative, 'reason': type(exc).__name__, 'resumable': False})
    return report
