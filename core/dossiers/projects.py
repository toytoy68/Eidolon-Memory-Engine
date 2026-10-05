# ==========================================================
# Projet      : Eidolon Memory Engine
# Organisation: Eidolon Core Technologies (ECT)
# Fichier     : core/dossiers/projects.py
# Description : Explicit Markdown project projections from Threads and linked Information.
# Standard    : Eidolon Presentation Standard v1
# ==========================================================

"""Explicit Markdown project projections from Threads and linked Information.

Generated text is reconstructible. Text outside the generated region is human
notes, preserved verbatim and not automatically ingested as canonical memory.
"""
from hashlib import sha256
from contextlib import ExitStack
import html
import json
import re
from pathlib import Path

from core.backend.filesystem import FilesystemBackend
from core.information.write_journal import InformationWriteJournal
from core.operations.filesystem import FilesystemOperationRepository
from core.operations.models import OperationStatus
from core.persistence import atomic_write_text, exclusive_write, has_symlink_component
from core.threads.storage import ThreadStorage


BEGIN = '<!-- BEGIN MEMORY-ENGINE GENERATED -->'
END = '<!-- END MEMORY-ENGINE GENERATED -->'
HUMAN = '# Notes humaines (non ingérées)\n\nÉcrire ici les notes humaines non ingérées.\n\n'


class DossierConflict(Exception):
    """Ambiguous or unfinished source/projection requires review."""


def _escaped_text(value):
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, sort_keys=True)
    return html.escape(text, quote=False)


def display(value):
    """Render one inline field, including Unicode and legacy line separators."""
    return ' '.join(_escaped_text(value).splitlines())


def quote(value):
    return '\n'.join('> ' + line for line in _escaped_text(value).splitlines())


class ProjectDossiers:
    def __init__(self, backend: FilesystemBackend, storage: ThreadStorage, root: Path):
        self.backend, self.storage, self.root = backend, storage, Path(root)
        if storage.persistent_root.resolve() != backend.persistent_root.resolve():
            raise DossierConflict('Thread and Information sources must share their Persistent root')
        if any(has_symlink_component(path) for path in (
            backend.persistent_root, backend.history_root, storage.threads_root,
        )):
            raise DossierConflict('canonical source contains a symlink')
        canonical = [backend.persistent_root.resolve(), backend.history_root.resolve()]
        output = self.root.resolve()
        if (has_symlink_component(self.root) or any(
            output == source or source in output.parents or output in source.parents for source in canonical
        )):
            raise DossierConflict('dossier output must be separate from canonical sources and history')

    def _path(self, thread_id):
        name = self.storage._path(thread_id).name
        path = self.root / name
        if has_symlink_component(path):
            raise DossierConflict('dossier path contains a symlink')
        return path

    @staticmethod
    def _read_text(path):
        # Human notes may use CRLF even when generated text uses LF.
        with path.open(encoding='utf-8', newline='') as handle:
            return handle.read()

    def _source(self, thread_id):
        from core.operations.read_phase import has_settled_audit
        settled = has_settled_audit(self.backend.persistent_root.parent.parent)
        from core.routing.execution_journal import require_available
        from core.operations.errors import OperationConflict
        if not settled:
            try:
                require_available(self.backend.history_root, thread_id=thread_id)
            except OperationConflict as exc:
                raise DossierConflict('pending routing execution requires recovery') from exc
        thread = self.storage.get(thread_id)
        dependencies = {}
        thread_path = self.storage._path(thread_id)
        dependencies['thread:' + thread_id] = sha256(thread_path.read_bytes()).hexdigest() if thread else None
        # Do not publish an APPLYING snapshot as a settled project recap.
        if not settled:
            for family in ('thread-create-v1', 'thread-status-v1', 'thread-delete-v1', 'thread-update-v1'):
                root = self.backend.history_root / 'operations' / family
                if has_symlink_component(root):
                    raise DossierConflict('Thread source journal contains a symlink')
                repository = FilesystemOperationRepository.__new__(FilesystemOperationRepository)
                repository.root = root
                for path in sorted(root.glob('*.json')):
                    operation = repository.get(path.stem)
                    if (operation and operation.target_id == thread_id
                            and operation.status is not OperationStatus.COMMITTED):
                        raise DossierConflict('pending Thread operation requires recovery')
        memories, missing = [], []
        ids = set()
        if thread is not None:
            for relation in thread.relations:
                if relation.get('type') != 'CONCERNS':
                    continue
                ids.add(relation.get('target_id', relation.get('target')))
        if not settled:
            journal = InformationWriteJournal(self.backend.history_root)
            for opid in journal.ids():
                entry = journal.read(opid)
                op = entry.operation if entry is not None else None
                if op and op.target_id in ids and op.status is not OperationStatus.COMMITTED:
                    raise DossierConflict('pending Information operation requires recovery')
        for information_id in sorted(ids):
            memory = self.backend.get(information_id)
            path = self.backend._path(information_id)
            dependencies['information:' + information_id] = sha256(path.read_bytes()).hexdigest() if memory else None
            if memory is None:
                missing.append(information_id)
            else:
                memories.append(memory)
        digest = sha256(json.dumps(dependencies, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
        return thread, memories, missing, digest

    @staticmethod
    def _generated(thread_id, source):
        thread, memories, missing, digest = source
        lines = [BEGIN, f'<!-- source-digest-v1: {digest} -->',
                 'Vue dérivée — vérifier sa fraîcheur avant réutilisation.', '']
        if thread is None:
            lines += [f'# Projet {display(thread_id)}', '', 'Thread source absent : aucun ancien résumé conservé dans cette zone.']
        else:
            lines += [f'# {display(thread.title)}', '',
                      f'Thread `{thread_id}`, revision {thread.revision}, statut **{thread.status.value}**.',
                      '', '## Objectif', '', quote(thread.objective), '', '## Récapitulatif sourcé', '']
            for memory in memories:
                state = memory.metadata.get('epistemic_status', 'NON RENSEIGNÉ')
                lines.append(f'- `{memory.information_id}` revision {memory.revision} — **{display(state)}** : '
                             + display(str(memory.content))[:180])
            if not memories:
                lines.append('Aucune Information liée disponible.')
            for title, kind in [('Décisions déclarées', 'DECISION'), ('Questions ouvertes', 'QUESTION')]:
                lines += ['', '## ' + title, '']
                selected = [memory for memory in memories if memory.metadata.get('type') == kind]
                lines += [f'- `{memory.information_id}` revision {memory.revision} : {display(memory.content)}' for memory in selected] or ['Aucune déclarée.']
            lines += ['', '## Actions', '']
            lines += [f'- [{action.status.value}] `{action.action_id}` : {display(action.description)}'
                      + (f' — {display(action.metadata)}' if action.metadata else '')
                      for action in thread.actions] or ['Aucune action déclarée.']
            keywords = sorted({word for memory in memories for word in memory.metadata.get('keywords', [])
                               if isinstance(word, str)})
            lines += ['', '## Mots-clés déclarés', '', display(', '.join(keywords)) or 'Aucun déclaré.',
                      '', '## Informations et sources', '']
            for memory in memories:
                lines += [f'### `{memory.information_id}` — revision {memory.revision}', '',
                          quote(memory.content), '',
                          'Contexte : ' + display(memory.metadata.get('context', {})), '',
                          'Provenance : ' + display(memory.provenance), '',
                          'Dates et échéances déclarées : ' + display(memory.temporal), '']
            for information_id in missing:
                lines += [f'Information `{information_id}` absente : contenu non recopié.', '']
        return '\n'.join(lines) + '\n' + END

    @staticmethod
    def _parts(text):
        if text.count(BEGIN) != 1 or text.count(END) != 1 or text.index(BEGIN) >= text.index(END):
            raise DossierConflict('generated section boundaries require manual review')
        before, rest = text.split(BEGIN, 1)
        generated, after = rest.split(END, 1)
        return before, BEGIN + generated + END, after

    def status(self, thread_id):
        """Read-only; use a stopped copy or rebuild's cooperative locks for consistency."""
        path = self._path(thread_id)
        if not path.exists():
            return {'status': 'MISSING', 'path': str(path)}
        source = self._source(thread_id)
        _, generated, _ = self._parts(self._read_text(path))
        return {'status': 'CURRENT' if generated == self._generated(thread_id, source) else 'STALE',
                'path': str(path), 'source_digest': source[3]}

    def read_notes(self, thread_id):
        """Read human sections and the exact document hash without initialization."""
        path = self._path(thread_id)
        if not path.is_file():
            raise DossierConflict('existing dossier required for notes')
        raw = path.read_bytes()
        before, _, after = self._parts(raw.decode('utf-8'))
        return {'before': before, 'after': after, 'document_sha256': sha256(raw).hexdigest(),
                'path': str(path), 'canonical_ingestion': False}

    def replace_notes(self, thread_id, *, before, after, expected_document_sha256):
        """Replace only explicit human sections if the whole snapshot is current."""
        if (not isinstance(before, str) or not isinstance(after, str)
                or any(marker in text for text in (before, after) for marker in (BEGIN, END))):
            raise DossierConflict('human notes must be text without generated section markers')
        before.encode('utf-8'); after.encode('utf-8')
        if (not isinstance(expected_document_sha256, str)
                or not re.fullmatch('[0-9a-f]{64}', expected_document_sha256)):
            raise DossierConflict('expected whole-document SHA256 required')
        path = self._path(thread_id)
        if not self.backend.persistent_root.is_dir() or not path.is_file():
            raise DossierConflict('existing engine and dossier required for notes')
        with ExitStack() as locks:
            locks.enter_context(exclusive_write(self.backend.persistent_root))
            if self.storage.threads_root.is_dir():
                locks.enter_context(exclusive_write(self.storage.threads_root))
            locks.enter_context(exclusive_write(self.root))
            from core.operations.readiness import check_readiness
            if not check_readiness(self.backend.persistent_root.parent.parent)['ready']:
                raise DossierConflict('recover or review before editing human notes')
            raw = path.read_bytes()
            if sha256(raw).hexdigest() != expected_document_sha256:
                raise DossierConflict('dossier changed; reread notes before editing')
            _, generated, _ = self._parts(raw.decode('utf-8'))
            updated = before + generated + after
            state = 'UNCHANGED' if updated.encode('utf-8') == raw else 'UPDATED'
            if state == 'UPDATED':
                atomic_write_text(path, updated)
            return {'status': state, 'path': str(path),
                    'document_sha256': sha256(updated.encode('utf-8')).hexdigest(),
                    'canonical_ingestion': False}

    def rebuild(self, thread_id):
        path = self._path(thread_id)
        with ExitStack() as locks:
            locks.enter_context(exclusive_write(self.backend.persistent_root))
            if self.storage.threads_root.is_dir():
                locks.enter_context(exclusive_write(self.storage.threads_root))
            source = self._source(thread_id)
            if source[0] is None and not path.exists():
                raise DossierConflict('cannot create dossier without a source Thread')
            self.root.mkdir(parents=True, exist_ok=True)
            with exclusive_write(self.root):
                previous = self._read_text(path) if path.exists() else None
                before, _, after = self._parts(previous) if previous is not None else (HUMAN, '', '\n')
                updated = before + self._generated(thread_id, source) + after
                if updated == previous:
                    state = 'UNCHANGED'
                else:
                    atomic_write_text(path, updated)
                    state = 'CREATED' if previous is None else 'UPDATED'
                    if source[0] is None:
                        state = 'SOURCE_REMOVED'
                return {'status': state, 'path': str(path), 'source_digest': source[3]}

    def resolve(self, information_id, *, selected_thread=None):
        """Use explicit CONCERNS links; never associate by words or similarity."""
        self.backend._path(information_id)
        candidates = []
        for path in sorted(self.storage.threads_root.glob('*.md')):
            thread = self.storage.get(path.stem)
            if thread is not None and any(
                relation.get('type') == 'CONCERNS'
                and relation.get('target_id', relation.get('target')) == information_id
                for relation in thread.relations
            ):
                candidates.append(thread.thread_id)
        if selected_thread is not None:
            if selected_thread not in candidates:
                raise DossierConflict('selected Thread is not explicitly linked to this Information')
            return {'status': 'LINK', 'thread_id': selected_thread, 'candidates': candidates}
        if len(candidates) == 1:
            return {'status': 'LINK', 'thread_id': candidates[0], 'candidates': candidates}
        return {'status': 'REVIEW' if candidates else 'UNASSIGNED', 'candidates': candidates}
