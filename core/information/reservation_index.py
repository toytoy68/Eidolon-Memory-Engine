"""Optional, reconstructible reservation index; journals remain authoritative.

Every lookup hashes all journal bytes. Only unchanged content can reuse an
earlier strict validation. No mtime/inode proof or process-wide cache is used.
"""
import hashlib
import re
from types import MappingProxyType

from core.information.write_journal import JournalReservations
from core.operations.errors import OperationConflict
from core.operations.models import OperationStatus
from core.persistence import atomic_write_text, has_symlink_component, write_lock_held
from core.storage_format import decode_json_value

VERSION = 1


def _json(value):
    from core.information.writes import canonical_json
    return canonical_json(value)


def _digest(value):
    return hashlib.sha256(_json(value).encode('utf-8')).hexdigest()


class ReservationIndex:
    def __init__(self, journal, writer=None):
        self.writer = writer
        self.journal = journal
        self.path = journal.operations_root.parent.parent.parent / 'derived/information-reservations-v1.json'

    def _boundary(self):
        if has_symlink_component(self.path) or (self.path.exists() and not self.path.is_file()):
            raise OperationConflict('invalid reservation index path')

    def enabled(self):
        self._boundary()
        return self.path.exists()

    def _locks(self):
        if self.writer is None or not all(write_lock_held(root) for root in
                   (self.writer.backend.persistent_root, self.writer.operations.root)):
            raise RuntimeError('reservation index requires Persistent and Operation locks')

    def _load(self):
        """Damaged/unknown derived state is discarded, never partially trusted."""
        self._boundary()
        try:
            value = decode_json_value(self.path.read_text(encoding='utf-8'))
            if (not isinstance(value, dict) or set(value) != {'version', 'entries', 'sha256'}
                    or type(value['version']) is not int or value['version'] != VERSION
                    or not isinstance(value['entries'], dict)
                    or value['sha256'] != _digest(dict(version=value['version'], entries=value['entries']))):
                return None
            for opid, row in value['entries'].items():
                if (not isinstance(opid, str) or not re.fullmatch(r'[A-Za-z0-9._-]+', opid)
                        or not isinstance(row, dict) or set(row) != {'sources', 'target', 'event', 'pending'}
                        or not isinstance(row['sources'], list) or len(row['sources']) != 2
                        or row['sources'] == [None, None]
                        or any(h is not None and (not isinstance(h, str) or not re.fullmatch(r'[0-9a-f]{64}', h))
                               for h in row['sources'])
                        or type(row['pending']) is not bool
                        or any(not isinstance(row[k], str) or not re.fullmatch(r'[A-Za-z0-9._-]+', row[k])
                               for k in ('target', 'event'))):
                    return None
            return value['entries']
        except (OSError, UnicodeError, ValueError, TypeError, KeyError):
            return None

    def _sources(self, opid):
        if not isinstance(opid, str) or not re.fullmatch(r'[A-Za-z0-9._-]+', opid):
            raise OperationConflict('invalid Information operation identity')
        hashes = []
        # IDs cannot contain a separator, roots were checked, and leaf links
        # are rejected below. Avoid resolving the same ancestors for every row.
        for root in (self.journal.operations_root, self.journal.receipts_root):
            path = root / f'{opid}.json'
            if path.is_symlink():
                raise OperationConflict('symbolic Information journal entry')
            try:
                hashes.append(hashlib.sha256(path.read_bytes()).hexdigest())
            except FileNotFoundError:
                hashes.append(None)
        return hashes

    def _build(self, old):
        self.journal._check_roots()
        entries, validated, reused = {}, 0, 0
        for opid in self.journal.ids():
            sources = self._sources(opid)
            if sources == [None, None]:
                raise OperationConflict('Information journal disappeared during index refresh')
            prior = old.get(opid) if old is not None else None
            if prior is not None and prior['sources'] == sources:
                entries[opid] = prior
                reused += 1
                continue
            entry = self.journal.read(opid)
            if entry is None or self._sources(opid) != sources:
                raise OperationConflict('Information journal changed during index validation')
            operation = entry.operation
            entries[opid] = dict(sources=sources, target=entry.result['information_id'],
                                 event=entry.result['event_id'],
                                 pending=operation is not None and operation.status is not OperationStatus.COMMITTED)
            validated += 1
        return entries, dict(entries=len(entries), validated=validated, reused=reused)

    @staticmethod
    def _view(entries):
        pending, events = {}, set()
        for opid, row in entries.items():
            events.add(row['event'])
            if row['pending']:
                pending.setdefault(row['target'], set()).add(opid)
        return JournalReservations(MappingProxyType({key: frozenset(value) for key, value in pending.items()}),
                                   frozenset(events))

    def refresh(self, *, rebuild=False):
        self._locks()
        self._boundary()
        old = None if rebuild else self._load()
        entries, report = self._build(old)
        if entries != old:
            payload = dict(version=VERSION, entries=entries)
            atomic_write_text(self.path, _json(dict(payload, sha256=_digest(payload))) + '\n')
        return self._view(entries), dict(status='CURRENT', **report)

    def status(self):
        """Read-only; use a stopped copy for a stable report."""
        self._boundary()
        if not self.path.exists():
            return dict(status='DISABLED')
        old = self._load()
        if old is None:
            return dict(status='REBUILD_REQUIRED', reason='invalid_index')
        self.journal._check_roots()
        ids = self.journal.ids()
        if set(ids) != set(old):
            return dict(status='STALE', reason='journal_membership_changed')
        if any(self._sources(opid) != old[opid]['sources'] for opid in ids):
            return dict(status='STALE', reason='journal_content_changed')
        return dict(status='CURRENT', entries=len(old))


def reservations(writer):
    index = ReservationIndex(writer.journal, writer)
    return index.refresh()[0] if index.enabled() else writer.journal.reservations()
