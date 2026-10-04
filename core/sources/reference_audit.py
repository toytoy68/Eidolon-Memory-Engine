"""Read-only, content-free warnings for present source-detail references."""
import re

from core.backend.filesystem import FilesystemBackend
from core.backend.errors import InvalidMemory
from core.persistence import has_symlink_component


def audit_references(root, snapshots):
    persistent = root / 'memory/persistent'
    if has_symlink_component(persistent):
        return []  # Existing inventory guards own unsafe trees.
    warnings = []
    for path in sorted(persistent.glob('source-detail-*.md')):
        if (not re.fullmatch(r'source-detail-(?:v2-)?[a-f0-9]{64}', path.stem)
                or path.is_symlink() or not path.is_file()):
            continue
        try:
            memory = FilesystemBackend._deserialize(path.read_text(encoding='utf-8'))
        except (OSError, UnicodeError, InvalidMemory):
            continue  # Format errors remain the responsibility of inventory.
        if memory.information_id != path.stem:
            continue
        fields = memory.provenance
        source = fields.get('source')
        source = source if isinstance(source, str) and re.fullmatch('[a-f0-9]{64}', source) else None
        snapshot = snapshots.get(source)
        paragraph = fields.get('paragraph')
        reasons = []
        if snapshot is None:
            reasons.append('source_or_extraction_unavailable')
        else:
            record, extraction = snapshot
            for name, current in (('source_sha256', record['sha256']),
                                  ('extractor', extraction['extractor']),
                                  ('extraction_sha256', extraction['text_sha256'])):
                if fields.get(name) != current:
                    reasons.append(name + '_mismatch')
            if type(paragraph) is not int or not 1 <= paragraph <= len(extraction['paragraphs']):
                reasons.append('paragraph_mismatch')
            elif (not isinstance(fields.get('quote'), str) or not fields['quote'].strip()
                  or fields['quote'] not in extraction['paragraphs'][paragraph - 1]):
                reasons.append('quote_mismatch')
        if reasons:
            warnings.append(dict(reason='source_reference_mismatch', information_id=memory.information_id,
                                 source_id=source, paragraph=paragraph if type(paragraph) is int else None,
                                 mismatches=reasons))
    return warnings
