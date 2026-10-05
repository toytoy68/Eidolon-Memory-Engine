# ==========================================================
# Projet      : Eidolon Memory Engine
# Organisation: Eidolon Core Technologies (ECT)
# Fichier     : core/indexing/catalogue.py
# Description : Disposable metadata catalogue. Discovery never promotes an entry to truth.
# Standard    : Eidolon Presentation Standard v1
# ==========================================================

"""Disposable metadata catalogue. Discovery never promotes an entry to truth."""
from contextlib import contextmanager, ExitStack
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path

from core.backend.filesystem import FilesystemBackend
from core.indexing.manifest import _build_manifest
from core.operations.errors import OperationConflict
from core.operations.readiness import check_readiness
from core.persistence import atomic_write_text, exclusive_write, has_symlink_component
from core.retrieval.ranking import lexical_ranking
from core.storage_format import decode_json_value
from core.threads.storage import ThreadStorage


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


class InformationCatalogue:
    """Fixed canonical roots; readers do not run repository constructors."""
    def __init__(self, root):
        self.root = Path(root)
        self.backend = FilesystemBackend.__new__(FilesystemBackend)
        self.backend.persistent_root = self.root / 'memory/persistent'
        self.backend.history_root = self.root / 'memory/history'
        self.backend.pending_delete_root = self.backend.history_root / 'pending-delete'
        self.storage = ThreadStorage.__new__(ThreadStorage)
        self.storage.persistent_root = self.backend.persistent_root
        self.storage.threads_root = self.backend.persistent_root / 'threads'
        self.directory = self.root / 'memory/catalogue'
        self.path = self.directory / 'information-v1.json'

    def _paths(self):
        for path in (self.backend.persistent_root, self.backend.history_root,
                     self.storage.threads_root, self.directory, self.path):
            if has_symlink_component(path):
                raise OperationConflict('catalogue path contains a symlink')
        if self.directory.exists() and not self.directory.is_dir():
            raise OperationConflict('catalogue output is not a directory')

    @contextmanager
    def _locks(self):
        self._paths()
        with ExitStack() as locks:
            locks.enter_context(exclusive_write(self.backend.persistent_root))
            if self.storage.threads_root.is_dir():
                locks.enter_context(exclusive_write(self.storage.threads_root))
            yield

    def _snapshot(self):
        self._paths()
        if not check_readiness(self.root)['ready']:
            raise OperationConflict('readiness blocks catalogue; recover or review first')
        entries = []

        def project(source, memory):
            metadata = memory.metadata
            qualification = metadata.get('qualification')
            entries.append(dict(
                information_id=memory.information_id, revision=memory.revision,
                file_sha256=source.file_sha256, pointer=f'memory/persistent/{memory.information_id}.md',
                type=metadata.get('type'),
                nature=qualification.get('nature') if isinstance(qualification, dict) else None,
                keywords=metadata.get('keywords', []), context=metadata.get('context', {}),
                epistemic_status=metadata.get('epistemic_status'),
                operational_state=metadata.get('operational_state'), retention=metadata.get('retention'),
                availability=metadata.get('availability'), recheck_required=bool(metadata.get('recheck_required')),
                temporal=memory.temporal,
            ))

        manifest = _build_manifest(self.backend.persistent_root, on_source=project)
        dependencies = {'information': manifest.digest, 'threads': {}, 'deletions': {}}
        projects = {}
        for thread in self.storage.list():
            path = self.storage._path(thread.thread_id)
            dependencies['threads'][thread.thread_id] = sha256(path.read_bytes()).hexdigest()
            for identity in self.storage._concerns(thread):
                projects.setdefault(identity, []).append(thread.thread_id)
        for source, entry in zip(manifest.entries, entries):
            raw = self.backend._path(source.information_id).read_bytes()
            if sha256(raw).hexdigest() != source.file_sha256:
                raise OperationConflict('catalogue source changed during scan')
            receipt_path = self.backend.pending_delete_root / (source.information_id + '.json')
            deletion_status = None
            if receipt_path.exists() or receipt_path.is_symlink():
                receipt = self.backend._load_delete_request(receipt_path, source.information_id)
                dependencies['deletions'][source.information_id] = sha256(receipt_path.read_bytes()).hexdigest()
                deletion_status = receipt['status']
            entry.update(project_ids=projects.get(source.information_id, []), deletion_status=deletion_status)
        return dict(format_version=1, policy='catalogue-metadata/1',
                    source_digest=sha256(canonical(dependencies).encode()).hexdigest(), entries=entries)

    def _state(self, expected):
        if not self.path.exists():
            return 'MISSING'
        try:
            actual = decode_json_value(self.path.read_text(encoding='utf-8'))
            if (not isinstance(actual, dict) or type(actual.get('format_version')) is not int
                    or actual['format_version'] != 1 or actual.get('policy') != 'catalogue-metadata/1'):
                return 'CORRUPT'
        except (OSError, ValueError):
            return 'CORRUPT'
        return 'CURRENT' if actual == expected else 'STALE'

    def status(self):
        """No writes, including no lock file. Stable only on a stopped copy."""
        expected = self._snapshot()
        return dict(status=self._state(expected), count=len(expected['entries']),
                    source_digest=expected['source_digest'], path=str(self.path))

    def rebuild(self):
        with self._locks():
            expected = self._snapshot()
            self.directory.mkdir(parents=True, exist_ok=True)
            with exclusive_write(self.directory):
                state = self._state(expected)
                if state != 'CURRENT':
                    atomic_write_text(self.path, canonical(expected) + '\n')
                if self._state(expected) != 'CURRENT':
                    raise OperationConflict('catalogue publication verification failed')
                return dict(status='UNCHANGED' if state == 'CURRENT' else 'REBUILT',
                            count=len(expected['entries']), source_digest=expected['source_digest'])

    def query(self, text='', *, limit=20, project_id=None, availability=None, epistemic_status=None):
        """Return metadata only after exact freshness check; never auto-rebuild."""
        if not isinstance(text, str) or type(limit) is not int or limit < 1:
            raise ValueError('text and positive integer limit required')
        with self._locks():
            expected = self._snapshot()
            state = self._state(expected)
            if state != 'CURRENT':
                raise OperationConflict(f'catalogue {state}; rebuild explicitly before querying')
            hits = []
            for entry in expected['entries']:
                if entry['deletion_status'] == 'PENDING_DELETE':
                    continue
                if project_id is not None and project_id not in entry['project_ids']:
                    continue
                if availability is not None and entry['availability'] != availability:
                    continue
                if epistemic_status is not None and entry['epistemic_status'] != epistemic_status:
                    continue
                rank = lexical_ranking(text, None, entry['information_id'], entry)
                if text.strip() and not rank.coverage:
                    continue
                hits.append(dict(entry, score=rank.score, ranking=rank.explanation()))
            hits.sort(key=lambda entry: (-entry['score'], entry['information_id']))
            return deepcopy(hits[:limit])
