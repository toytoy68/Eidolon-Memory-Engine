"""Immutable original-source bundles; no canonical-memory ingestion."""
from datetime import datetime
from hashlib import sha256
import json
import os
from pathlib import Path
import re

from core.persistence import exclusive_write, has_symlink_component, atomic_write_text
from core.storage_format import decode_json_value

MAX_BYTES = 10 * 1024 * 1024
EXTENSIONS = {'.docx', '.pdf', '.txt', '.md'}
KEYS = {'format_version', 'source_id', 'sha256', 'title', 'author', 'added_at', 'original_name', 'size'}


def _text(value, name, maximum, *, empty=False):
    if (not isinstance(value, str) or len(value) > maximum or (not empty and not value.strip())
            or any(ord(c) < 32 or ord(c) == 127 for c in value)):
        raise ValueError(f'invalid source {name}')
    return value


def _fields(name, title, author, added_at):
    _text(name, 'filename', 255)
    if '/' in name or '\\' in name or Path(name).suffix.lower() not in EXTENSIONS:
        raise ValueError('source must be a DOCX, PDF, TXT or Markdown basename')
    _text(title, 'title', 512)
    _text(author, 'author', 256, empty=True)
    _text(added_at, 'date', 64)
    instant = datetime.fromisoformat(added_at.replace('Z', '+00:00'))
    if instant.tzinfo is None or instant.utcoffset() is None:
        raise ValueError('source date requires a timezone')


class SourceStore:
    def __init__(self, root):
        self.root = Path(root)
        self.directory = self.root / 'memory/sources'

    def _paths(self):
        if has_symlink_component(self.directory) or not self.root.is_dir():
            raise ValueError('unsafe source tree')
        if self.directory.exists() and not self.directory.is_dir():
            raise ValueError('source directory is not a directory')

    @staticmethod
    def _checkpoint(stage):
        """Fault-injection boundary after durable staging/publication."""

    def _bundle(self, path, identity):
        self._paths()
        if (not re.fullmatch('[a-f0-9]{64}', identity) or has_symlink_component(path)
                or not path.is_dir() or {p.name for p in path.iterdir()} not in
                    ({'metadata.json', 'original'}, {'metadata.json', 'original', 'extraction.json'})):
            raise ValueError('invalid source bundle')
        meta, original = path / 'metadata.json', path / 'original'
        for file, maximum in ((meta, 16384), (original, MAX_BYTES)):
            if file.is_symlink() or not file.is_file() or file.stat().st_size > maximum:
                raise ValueError('unsafe or oversized source file')
        record = decode_json_value(meta.read_text(encoding='utf-8'))
        if not isinstance(record, dict) or set(record) != KEYS or type(record['format_version']) is not int or record['format_version'] != 1:
            raise ValueError('invalid source metadata')
        _fields(record['original_name'], record['title'], record['author'], record['added_at'])
        with original.open('rb') as handle:
            data = handle.read(MAX_BYTES+1)
        if (not 0 < len(data) <= MAX_BYTES or type(record['size']) is not int
                or record['size'] != len(data) or record['source_id'] != identity
                or record['sha256'] != identity or sha256(data).hexdigest() != identity):
            raise ValueError('source original or identity differs from metadata')
        if (path / 'extraction.json').exists():
            from core.sources.extraction import extract_paragraphs
            if self._extraction(path, identity) != extract_paragraphs(record, data):
                raise ValueError('frozen extraction differs from original source')
        return record, data

    def _extraction(self, path, identity):
        from core.sources.extraction import MAX_TEXT_BYTES, validate_extraction
        file = path / 'extraction.json'
        if file.is_symlink() or not file.is_file() or file.stat().st_size > MAX_TEXT_BYTES * 6 + 4096:
            raise ValueError('unsafe source extraction file')
        return validate_extraction(decode_json_value(file.read_text(encoding='utf-8')), identity)

    def extraction(self, identity):
        self.read(identity)
        return self._extraction(self.directory / identity, identity)

    def extract(self, identity):
        self._paths()
        with exclusive_write(self.root / 'memory/persistent'), exclusive_write(self.directory):
            from core.operations.readiness import check_readiness
            if not check_readiness(self.root)['ready']:
                raise ValueError('readiness blocks source extraction')
            record, data = self.read(identity)
            path = self.directory / identity
            if (path / 'extraction.json').exists():
                return dict(status='UNCHANGED', extraction=self._extraction(path, identity))
            from core.sources.extraction import extract_paragraphs
            result = extract_paragraphs(record, data)
            from core.operations.read_phase import invalidate_publication
            invalidate_publication(self.root / 'memory/persistent')
            atomic_write_text(path / 'extraction.json', json.dumps(result, ensure_ascii=False, sort_keys=True)+'\n')
            return dict(status='EXTRACTED', extraction=self._extraction(path, identity))

    def read(self, identity):
        if not isinstance(identity, str) or not re.fullmatch('[a-f0-9]{64}', identity):
            raise ValueError('invalid source identity')
        return self._bundle(self.directory / identity, identity)

    def list(self):
        self._paths()
        records = []
        if self.directory.exists():
            for path in sorted(self.directory.iterdir()):
                if path.name == '.write.lock' and path.is_file() and not path.is_symlink():
                    continue
                records.append(self.read(path.name)[0])
        return records

    def inspect(self):
        """Read-only library view; isolate invalid bundles without relaxing audits."""
        self._paths()
        report = dict(sources=[], pending=[], issues=[])
        if not self.directory.exists():
            return report
        for path in sorted(self.directory.iterdir()):
            try:
                if path.name == '.write.lock' and path.is_file() and not path.is_symlink():
                    continue
                if path.name.startswith('.pending-'):
                    record, _ = self._bundle(path, path.name.removeprefix('.pending-'))
                    report['pending'].append(record)
                else:
                    report['sources'].append(self.read(path.name)[0])
            except (OSError, ValueError, TypeError, KeyError) as exc:
                report['issues'].append(dict(path=path.relative_to(self.root).as_posix(), reason=str(exc)))
        return report

    def add(self, content, *, original_name, title, author, added_at):
        _fields(original_name, title, author, added_at)
        if not isinstance(content, bytes) or not 0 < len(content) <= MAX_BYTES:
            raise ValueError('source must contain 1 byte to 10 MiB')
        # Resolve runtime dependencies before creating any publication stage.
        from core.migration.converter import _atomic_bytes
        from core.migration.core_copy import _publish
        self._paths()
        persistent = self.root / 'memory/persistent'
        if not persistent.is_dir():
            raise ValueError('initialized core Persistent directory required')
        identity = sha256(content).hexdigest()
        record = dict(format_version=1, source_id=identity, sha256=identity, size=len(content),
                      original_name=original_name, title=title, author=author, added_at=added_at)
        with exclusive_write(persistent):
            self._paths()
            self.directory.mkdir(exist_ok=True)
            with exclusive_write(self.directory):
                from core.operations.readiness import check_readiness
                from core.operations.read_phase import invalidate_publication
                stage = self.directory / ('.pending-' + identity)
                pending_path = stage.relative_to(self.root).as_posix()
                state = check_readiness(self.root)
                if any(issue['path'] != pending_path or issue['reason'] != 'pending_source_publication'
                       for issue in state['issues']):
                    raise ValueError('readiness blocks source publication')
                target = self.directory / identity
                if target.exists() or target.is_symlink():
                    existing, data = self.read(identity)
                    if data != content:
                        raise ValueError('source hash collision')
                    return dict(status='UNCHANGED', source=existing)
                invalidate_publication(persistent)
                if stage.exists() or stage.is_symlink():
                    prepared, data = self._bundle(stage, identity)
                    if data != content or any(prepared[k] != record[k] for k in ('original_name', 'title', 'author')):
                        raise ValueError('pending source requires the same upload metadata')
                    record = prepared
                else:
                    stage.mkdir()
                    _atomic_bytes(stage / 'original', content)
                    atomic_write_text(stage / 'metadata.json', json.dumps(record, ensure_ascii=False, sort_keys=True)+'\n')
                    self._bundle(stage, identity)
                self._checkpoint('after_staging')
                # Same Linux NOREPLACE primitive used by core-tree transfers.
                _publish(stage, target)
                invalidate_publication(persistent)
                self._checkpoint('after_publication')
                return dict(status='ADDED', source=self.read(identity)[0])


def audit_sources(root):
    store = SourceStore(root)
    report = dict(count=0, issues=[])
    try:
        store._paths()
        if not store.directory.exists():
            return report
        for path in sorted(store.directory.iterdir()):
            try:
                if path.name == '.write.lock' and path.is_file() and not path.is_symlink():
                    continue
                if path.name.startswith('.pending-'):
                    store._bundle(path, path.name.removeprefix('.pending-'))
                    raise ValueError('pending_source_publication')
                store.read(path.name)
                report['count'] += 1
            except (OSError, ValueError, TypeError, KeyError) as exc:
                report['issues'].append(dict(path=path.relative_to(store.root).as_posix(), reason=str(exc)))
    except (OSError, ValueError) as exc:
        report['issues'].append(dict(path='memory/sources', reason=str(exc)))
    return report
