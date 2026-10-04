"""Durable, content-free extraction identities. Readers never create files."""
from datetime import datetime, timezone
import re

from core.persistence import has_symlink_component
from core.storage_format import decode_json_value

FAMILY = 'source-extractions-v1'
KEYS = {'format_version', 'source_id', 'source_sha256', 'extractor',
        'text_sha256', 'paragraph_count', 'committed_at'}


def directory(root):
    return root / 'memory/history' / FAMILY


def validate(value, identity):
    if not isinstance(value, dict) or set(value) != KEYS:
        raise ValueError('invalid extraction commitment fields')
    if (type(value['format_version']) is not int or value['format_version'] != 1
            or not re.fullmatch('[a-f0-9]{64}', identity)
            or value['source_id'] != identity or value['source_sha256'] != identity
            or not isinstance(value['text_sha256'], str)
            or not re.fullmatch('[a-f0-9]{64}', value['text_sha256'])
            or type(value['paragraph_count']) is not int or value['paragraph_count'] < 1
            or not isinstance(value['extractor'], str) or not 1 <= len(value['extractor']) <= 128
            or any(ord(c) < 32 for c in value['extractor'])
            or not isinstance(value['committed_at'], str) or len(value['committed_at']) > 64):
        raise ValueError('invalid extraction commitment identity')
    instant = datetime.fromisoformat(value['committed_at'].replace('Z', '+00:00'))
    if instant.tzinfo is None or instant.utcoffset() is None:
        raise ValueError('extraction commitment requires a timezone')
    return value


def read(root, identity):
    path = directory(root) / (identity + '.json')
    if has_symlink_component(path):
        raise ValueError('unsafe extraction commitment path')
    family = path.parent
    if family.exists() and not family.is_dir():
        raise ValueError('invalid extraction commitment directory')
    if not path.exists():
        return None
    if not path.is_file() or path.stat().st_size > 16384:
        raise ValueError('unsafe or oversized extraction commitment')
    return validate(decode_json_value(path.read_text(encoding='utf-8')), identity)


def matches(commitment, extraction):
    return (commitment['source_sha256'] == extraction['source_sha256']
            and commitment['extractor'] == extraction['extractor']
            and commitment['text_sha256'] == extraction['text_sha256']
            and commitment['paragraph_count'] == len(extraction['paragraphs']))


def prepare(identity, extraction):
    return validate(dict(format_version=1, source_id=identity,
                         source_sha256=extraction['source_sha256'], extractor=extraction['extractor'],
                         text_sha256=extraction['text_sha256'], paragraph_count=len(extraction['paragraphs']),
                         committed_at=datetime.now(timezone.utc).isoformat()), identity)


def audit(root, snapshots, valid_sources):
    issues, information, committed = [], [], set()
    family = directory(root)
    try:
        if has_symlink_component(family) or (family.exists() and not family.is_dir()):
            raise ValueError('unsafe extraction commitment directory')
        for path in sorted(family.iterdir()) if family.exists() else []:
            relative = path.relative_to(root).as_posix()
            try:
                if path.name == '.write.lock' and path.is_file() and not path.is_symlink():
                    continue
                if not re.fullmatch('[a-f0-9]{64}\\.json', path.name):
                    raise ValueError('invalid extraction commitment entry')
                committed.add(path.stem)
                frozen = read(root, path.stem)
                if path.stem not in valid_sources:
                    raise ValueError('extraction_commitment_source_unavailable')
                if path.stem not in snapshots:
                    from core.sources.store import SourceStore
                    from core.sources.extraction import reproduce_extraction
                    record, original = SourceStore(root).read(path.stem)
                    expected = reproduce_extraction(record, original, extractor=frozen['extractor'])
                    if not matches(frozen, expected):
                        raise ValueError('extraction_commitment_mismatch')
                    raise ValueError('pending_source_extraction')
                if not matches(frozen, snapshots[path.stem][1]):
                    raise ValueError('extraction_commitment_mismatch')
            except (OSError, ValueError, TypeError, KeyError) as exc:
                issues.append(dict(path=relative, reason=str(exc)))
    except (OSError, ValueError) as exc:
        issues.append(dict(path=family.relative_to(root).as_posix(), reason=str(exc)))
    for identity in sorted(set(snapshots) - committed):
        information.append(dict(source_id=identity, reason='uncommitted_extraction'))
    return issues, information
