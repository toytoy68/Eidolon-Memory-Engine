"""Preview or explicitly execute a qualified plan on an existing engine tree."""
import argparse
from dataclasses import asdict
import json
from pathlib import Path

from core.backend.filesystem import FilesystemBackend
from core.backend.models import Memory
from core.backend.errors import BackendError
from core.dossiers.projects import DossierConflict
from core.operations.errors import OperationRepositoryError
from core.routing.execution import RoutingExecutor, restore_context
from core.storage_format import decode_json_value
from core.threads.storage import ThreadStorageError
from core.threads.manager import ThreadError


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    sub = parser.add_subparsers(dest='action', required=True)
    assess = sub.add_parser('assess', help='Read-only NONE/REVIEW outcome and next explicit step')
    assess.add_argument('--memory', type=Path, required=True)
    assess.add_argument('--context', type=Path, required=True)
    preview = sub.add_parser('preview')
    preview.add_argument('--memory', type=Path, required=True)
    preview.add_argument('--context', type=Path, required=True)
    project = preview.add_mutually_exclusive_group(required=True)
    project.add_argument('--project-revision', type=int)
    project.add_argument('--new-project', type=Path, help='Explicit new Thread JSON template; version 3 includes lifecycle')
    preview.add_argument('--with-lifecycle', action='store_true', help='Version 2: persist availability and register proposed deadline')
    preview.add_argument('--link-only', action='store_true', help='Version 4: link exact already-stored Information without writing it')
    execute = sub.add_parser('execute')
    execute.add_argument('--plan', type=Path, required=True)
    execute.add_argument('--intent-id', required=True)
    execute.add_argument('--actor', required=True)
    execute.add_argument('--timestamp', required=True)
    recall = sub.add_parser('recall')
    recall.add_argument('query')
    recall.add_argument('--scope', type=Path, required=True)
    recall.add_argument('--at')
    recall.add_argument('--mode', choices=['operational', 'historical'], default='operational')
    recall.add_argument('--project-id')
    recall.add_argument('--max-chars', type=int, default=4000)
    args = parser.parse_args(argv)
    try:
        # A reader facade avoids constructor mkdir during preview.
        backend = FilesystemBackend.__new__(FilesystemBackend)
        backend.persistent_root = args.root / 'memory/persistent'
        backend.history_root = args.root / 'memory/history'
        backend.pending_delete_root = backend.history_root / 'pending-delete'
        executor = RoutingExecutor(backend)
        if args.action == 'assess':
            memory = Memory(**decode_json_value(args.memory.read_text(encoding='utf-8')))
            context = restore_context(decode_json_value(args.context.read_text(encoding='utf-8')))
            result = executor.assess(memory, context)
        elif args.action == 'preview':
            memory = Memory(**decode_json_value(args.memory.read_text(encoding='utf-8')))
            context = restore_context(decode_json_value(args.context.read_text(encoding='utf-8')))
            if args.link_only:
                if args.new_project is not None or args.with_lifecycle:
                    raise ValueError('link-only requires an existing project and excludes lifecycle writes')
                result = executor.preview_link(memory, context, project_revision=args.project_revision)
            elif args.new_project is not None:
                from core.storage_format import encode_document
                template = executor.storage._deserialize(encode_document('Thread',
                    decode_json_value(args.new_project.read_text(encoding='utf-8'))))
                result = executor.preview_new_project(memory, context, project=template)
            else:
                result = executor.preview(memory, context, project_revision=args.project_revision,
                                          include_lifecycle=args.with_lifecycle)
        elif args.action == 'recall':
            result = asdict(executor.recall(args.query,
                            query_scope=decode_json_value(args.scope.read_text(encoding='utf-8')),
                            at=args.at, mode=args.mode, project_id=args.project_id, max_chars=args.max_chars))
        else:
            prepared = decode_json_value(args.plan.read_text(encoding='utf-8'))
            if isinstance(prepared, dict) and prepared.get('format_version') == 3:
                backend = FilesystemBackend(backend.persistent_root, backend.history_root)
                executor = RoutingExecutor(backend)
            result = executor.execute(prepared, intent_id=args.intent_id, actor=args.actor, timestamp=args.timestamp)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (OSError, ValueError, TypeError, KeyError, BackendError, OperationRepositoryError,
            ThreadStorageError, ThreadError, DossierConflict) as exc:
        print(json.dumps({'status': 'BLOCKED', 'error': type(exc).__name__, 'reason': str(exc)}, ensure_ascii=False))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
