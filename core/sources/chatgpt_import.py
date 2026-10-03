"""Import conversation archives as UNVERIFIED observations into an isolated core root.

No semantic extraction, model invocation, automatic confirmation or branch merging.
"""
import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path

from core.backend.filesystem import FilesystemBackend
from core.backend.models import Memory
from core.information.writes import FilesystemInformationWrites
from core.migration.converter import _atomic_bytes
from core.storage_format import decode_json_value


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
        author = message.get('author', {}).get('role')
        content = message.get('content', {})
        if author not in {'user', 'assistant'} or content.get('content_type') not in {'text', 'multimodal_text', 'code'}:
            continue
        if message.get('channel') not in {None, 'final', 'commentary'}:
            continue
        parts = content.get('parts', [])
        text = '\n'.join(p for p in parts if isinstance(p, str))
        if not text.strip():
            continue
        messages.append(dict(node_id=node_id, message_id=message.get('id'), parent=node.get('parent'),
            role=author, created_at=message.get('create_time'), content=text))
    if not messages:
        return None, at
    canonical = json.dumps(conversation, ensure_ascii=False, sort_keys=True, allow_nan=False).encode()
    digest = sha256(canonical).hexdigest()
    identity = 'gpt-conversation-v1-' + digest
    content = json.dumps(dict(title=conversation.get('title', ''), conversation_id=cid,
        current_node=conversation.get('current_node'), messages=messages), ensure_ascii=False, indent=2)
    memory = Memory(identity, content=content,
        metadata=dict(type='OBSERVATION', epistemic_status='UNVERIFIED', corpus='chatgpt-export-test',
            archive_kind='conversation', message_count=len(messages)),
        temporal=dict(observed_at=at),
        provenance=dict(source_type='USER_EXPORT', source_sha256=source_hash,
            conversation_id=cid, conversation_sha256=digest, importer='chatgpt-archive-v1',
            historical_archive=True, semantic_facts_extracted=False))
    return memory, at


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
    root.mkdir(parents=True, exist_ok=True)
    marker.write_text('Isolated conversation archives; not confirmed personal facts.\n')
    backend = FilesystemBackend(root / 'memory/persistent', root / 'memory/history')
    writer = FilesystemInformationWrites(backend)
    directory = root / 'import-originals'
    directory.mkdir(exist_ok=True)
    for digest, raw in originals:
        target = directory / (digest + '.json')
        if target.exists():
            if target.read_bytes() != raw:
                raise ValueError('original export differs from hash')
        else:
            _atomic_bytes(target, raw)
    for memory, at in plans:
        identity = memory.information_id
        writer.create(memory, operation_id='import-' + identity, event_id='event-' + identity,
            actor='chatgpt-export-importer', timestamp=at)
    return dict(conversations=len(plans), messages=sum(m.metadata['message_count'] for m, _ in plans),
        originals=len(originals), status='IMPORTED', semantic_facts_extracted=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('files', nargs='+', type=Path)
    args = parser.parse_args()
    print(json.dumps(import_exports(args.root, args.files)))


if __name__ == '__main__':
    main()
