# ==========================================================
# Projet      : Eidolon Memory Engine
# Organisation: Eidolon Core Technologies (ECT)
# Fichier     : core/sources/chatgpt_import.py
# Description : Import conversation archives as UNVERIFIED observations into an isolated core root.
# Standard    : Eidolon Presentation Standard v1
# ==========================================================

"""Import conversation archives as UNVERIFIED observations into an isolated core root.

No semantic extraction, model invocation, automatic confirmation or branch merging.
"""
import argparse
from dataclasses import replace
from datetime import datetime, timezone
from hashlib import sha256
import json
import re
from pathlib import Path

from core.backend.filesystem import FilesystemBackend
from core.backend.models import Memory
from core.backend.errors import BackendError
from core.operations.errors import OperationRepositoryError
from core.persistence import exclusive_write
from core.information.writes import FilesystemInformationWrites, fingerprint
from core.operations.models import OperationType, OperationStatus
from core.migration.converter import _atomic_bytes
from core.storage_format import decode_json_value


IMPORTER = 'chatgpt-archive-v2'
# v1 kept tool calls (recipient other than 'all') and hidden context messages.
# Its archives stay readable and recallable; they are never rewritten.
ARCHIVE_IMPORTERS = frozenset({'chatgpt-archive-v1', IMPORTER})


class ImportBlocked(ValueError):
    """A blocked publication reports completed steps, never implicit rollback."""
    def __init__(self, reason, progress):
        super().__init__(reason)
        self.progress = dict(progress)


def _original_hashes(directory):
    """Verify retained originals before using their hashes for command replay."""
    hashes = []
    for path in sorted(directory.glob('*.json')):
        if (path.is_symlink() or not path.is_file()
                or not re.fullmatch(r'[a-f0-9]{64}', path.stem)
                or path.stat().st_size > 32 * 1024 * 1024
                or sha256(path.read_bytes()).hexdigest() != path.stem):
            raise ValueError('invalid retained original export')
        hashes.append(path.stem)
    return hashes


def _resolve_commands(writer, plans, directory):
    """Preflight the whole lot under writer locks, including compact receipts.

    Only substitute source_sha256 when the original retained export recreates
    the exact journal fingerprint. Never relax the generic writer's guard.
    New occurrences remain traceable in their exact original exports.
    """
    resolved, originals = [], None
    for memory, at in plans:
        identity = memory.information_id
        entry = writer.journal.read('import-' + identity)
        if entry is None:
            if writer.backend.get(identity) is not None:
                raise ValueError('archive exists without its original command')
            writer._check_deletion(OperationType.INFORMATION_CREATE, identity)
            resolved.append((memory, at, False))
            continue
        if entry.operation is not None and entry.operation.status is OperationStatus.FAILED:
            raise ValueError('failed import operation requires manual resolution')
        if originals is None:
            originals = _original_hashes(directory)
        for source_hash in originals:
            candidate = replace(memory, provenance={**memory.provenance, 'source_sha256': source_hash})
            digest = fingerprint(OperationType.INFORMATION_CREATE, candidate, 0,
                'event-' + identity, 'chatgpt-export-importer', at)
            if digest == entry.fingerprint:
                resolved.append((candidate, at, True))
                break
        else:
            raise ValueError('cannot reconstruct original command from retained exports')
    return resolved


def is_conversation_archive(memory):
    return (memory.metadata.get('archive_kind') == 'conversation'
            and memory.provenance.get('importer') in ARCHIVE_IMPORTERS)


def plan_conversation(conversation, source_hash):
    if not isinstance(conversation, dict):
        raise ValueError('invalid conversation')
    cid = conversation.get('id') or conversation.get('conversation_id')
    mapping = conversation.get('mapping')
    if not isinstance(cid, str) or not cid or not isinstance(mapping, dict):
        raise ValueError('conversation identity and mapping required')
    stamp = conversation.get('create_time')
    if not isinstance(stamp, (int, float)):
        raise ValueError('conversation date required')
    at = datetime.fromtimestamp(stamp, timezone.utc).isoformat()
    # Node IDs and parent links preserve alternatives; never concatenate branches as one dialogue.
    messages = []
    for node_id, node in mapping.items():
        if not isinstance(node, dict):
            raise ValueError('invalid conversation node')
        message = node.get('message')
        if not isinstance(message, dict):
            continue
        author, content = message.get('author'), message.get('content')
        if not isinstance(author, dict) or not isinstance(content, dict):
            raise ValueError('invalid conversation message')
        author = author.get('role')
        if author not in {'user', 'assistant'} or content.get('content_type') not in {'text', 'multimodal_text'}:
            continue
        if message.get('channel') not in {None, 'final', 'commentary'}:
            continue
        # Tool calls and hidden context are technical messages, not dialogue.
        metadata = message.get('metadata')
        if (message.get('recipient', 'all') != 'all'
                or (isinstance(metadata, dict) and metadata.get('is_visually_hidden_from_conversation') is True)):
            continue
        parts = content.get('parts', [])
        if not isinstance(parts, list):
            raise ValueError('conversation content.parts must be a list')
        text = '\n'.join(p for p in parts if isinstance(p, str))
        if not text.strip():
            continue
        messages.append(dict(node_id=node_id, message_id=message.get('id'), parent=node.get('parent'),
            role=author, created_at=message.get('create_time'), content=text))
    if not messages:
        return None, at
    canonical = json.dumps(conversation, ensure_ascii=False, sort_keys=True, allow_nan=False).encode()
    digest = sha256(canonical).hexdigest()
    identity = 'gpt-conversation-v2-' + digest
    content = json.dumps(dict(title=conversation.get('title', ''), conversation_id=cid,
        current_node=conversation.get('current_node'), messages=messages), ensure_ascii=False, indent=2)
    memory = Memory(identity, content=content,
        metadata=dict(type='OBSERVATION', epistemic_status='UNVERIFIED', corpus='chatgpt-export-test',
            archive_kind='conversation', message_count=len(messages)),
        temporal=dict(observed_at=at),
        provenance=dict(source_type='USER_EXPORT', source_sha256=source_hash,
            conversation_id=cid, conversation_sha256=digest, importer=IMPORTER,
            historical_archive=True, semantic_facts_extracted=False))
    return memory, at


def _check_import_version(root):
    persistent = root / 'memory/persistent'
    history = root / 'memory/history'
    if (any(persistent.glob('gpt-conversation-v1-*.md'))
            or any(any((history / family / 'information-write-v1').glob('import-gpt-conversation-v1-*.json'))
                   for family in ('operations', 'operation-receipts'))):
        raise ValueError('existing v1 ChatGPT corpus: import v2 archives into a new root')


def import_exports(root, files):
    root = Path(root)
    # Validate all inputs before any publication. Reject conflicting versions explicitly.
    plans, originals, identities = [], [], {}
    for filename in files:
        path = Path(filename)
        if path.is_symlink() or not path.is_file() or path.stat().st_size > 32 * 1024 * 1024:
            raise ValueError('unsafe or oversized export')
        raw = path.read_bytes()
        source_hash = sha256(raw).hexdigest()
        value = decode_json_value(raw.decode('utf-8-sig'))
        if not isinstance(value, list):
            raise ValueError('export must be a list of conversations')
        originals.append((source_hash, raw))
        for conversation in value:
            memory, at = plan_conversation(conversation, source_hash)
            if memory is None:
                continue
            cid = memory.provenance['conversation_id']
            digest = memory.provenance['conversation_sha256']
            if cid in identities:
                if identities[cid] != digest:
                    raise ValueError('conflicting conversation versions in import batch')
                continue
            identities[cid] = digest
            plans.append((memory, at))
    marker = root / 'CHATGPT-TEST-CORPUS'
    if root.exists() and any(root.iterdir()) and not marker.is_file():
        raise ValueError('nonempty destination must be an existing ChatGPT test corpus')
    _check_import_version(root)
    root.mkdir(parents=True, exist_ok=True)
    try:
        with marker.open('x', encoding='utf-8') as handle:
            handle.write('Isolated conversation archives; not confirmed personal facts.\n')
    except FileExistsError:
        pass
    backend = FilesystemBackend(root / 'memory/persistent', root / 'memory/history')
    writer = FilesystemInformationWrites(backend)
    progress = dict(new_conversations=0, replayed_conversations=0, new_originals=0,
                    publication_attempted=False)
    with (exclusive_write(root / 'memory/persistent'), exclusive_write(writer.operations.root),
          exclusive_write(writer.events.events_root)):
        _check_import_version(root)
        directory = root / 'import-originals'
        try:
            commands = _resolve_commands(writer, plans, directory)
            # Validate every existing original before publishing any new one.
            for digest, raw in originals:
                target = directory / (digest + '.json')
                if target.is_symlink() or (target.exists() and target.read_bytes() != raw):
                    raise ValueError('original export differs from hash')
            directory.mkdir(exist_ok=True)
            for digest, raw in originals:
                target = directory / (digest + '.json')
                if not target.exists():
                    progress['publication_attempted'] = True
                    _atomic_bytes(target, raw)
                    progress['new_originals'] += 1
            for memory, at, replay in commands:
                identity = memory.information_id
                progress['publication_attempted'] = True
                writer.create(memory, operation_id='import-' + identity, event_id='event-' + identity,
                    actor='chatgpt-export-importer', timestamp=at)
                progress['replayed_conversations' if replay else 'new_conversations'] += 1
        except (ValueError, OSError, TypeError, BackendError, OperationRepositoryError) as exc:
            raise ImportBlocked(str(exc), progress) from exc
    return dict(conversations=len(plans), messages=sum(m.metadata['message_count'] for m, _ in plans),
        originals=len(originals), status='IMPORTED', semantic_facts_extracted=False, **progress)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('files', nargs='+', type=Path)
    args = parser.parse_args(argv)
    try:
        result = import_exports(args.root, args.files)
    except (ValueError, OSError, TypeError, BackendError, OperationRepositoryError) as exc:
        result = dict(status='BLOCKED', reason=str(exc))
        if isinstance(exc, ImportBlocked):
            result['progress'] = exc.progress
    print(json.dumps(result))
    return int(result['status'] == 'BLOCKED')


if __name__ == '__main__':
    raise SystemExit(main())
