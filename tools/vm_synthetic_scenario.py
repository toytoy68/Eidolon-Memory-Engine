"""Build and verify a disposable VM scenario; refuse any populated root."""
from dataclasses import asdict, replace
from hashlib import sha256
import argparse
import json
from pathlib import Path

from core.backend.filesystem import FilesystemBackend
from core.backend.models import Memory
from core.dossiers.projects import DossierConflict
from core.information.writes import FilesystemInformationWrites
from core.lifecycle.service import LifecycleTriggers
from core.maintenance.service import MaintenancePass
from core.operations.readiness import check_readiness, recover_all
from core.persistence import has_symlink_component
from core.routing.execution import RoutingExecutor
from core.routing.policy import RoutingContext, TargetRevision
from core.threads.models import Thread
from core.threads.service import ThreadService

STAMP = '2026-10-03T01:20:00Z'
DUE = '2026-10-04T01:20:00Z'
SCOPE = {'goal': 'synthetic-vm-acceptance'}


def run(root):
    root = Path(root).absolute()
    if has_symlink_component(root) or not root.is_dir() or any(root.iterdir()):
        raise ValueError('scenario requires an existing empty disposable directory without symlinks')
    backend = FilesystemBackend(root / 'memory/persistent', root / 'memory/history')
    executor = RoutingExecutor(backend)
    results = {}

    def memory(identity, *, scheduled=False, project=False):
        context = {'scope': SCOPE}
        if project:
            context['project_id'] = 'project'
        return Memory(identity, content='Synthetic measurement ' + identity,
            metadata={'qualification': {'version': '0.1', 'nature': 'TECHNICAL', 'qualified_by': 'synthetic-human'},
                      'epistemic_status': 'UNVERIFIED', 'context': context},
            provenance={'source': 'synthetic-fixture', 'author_role': 'ADMIN'},
            verification={'evidence': {'fixture': True}}, temporal={'resume_at': DUE} if scheduled else {})

    def execute(prepared, identity):
        result = executor.execute(prepared, intent_id=identity, actor='synthetic-human', timestamp=STAMP)
        assert executor.execute(prepared, intent_id=identity, actor='synthetic-human', timestamp=STAMP) == result
        results[identity] = result
        return result

    for index in range(10):
        value = memory('info-' + str(index), scheduled=index % 3 == 0)
        execute(executor.preview_information(value, RoutingContext(query_scope=SCOPE)), 'store-' + str(index))
    value = memory('project-source', project=True)
    project = Thread('project', 'Synthetic project', 'Verify explicit journeys', created_at=STAMP, updated_at=STAMP)
    execute(executor.preview_new_project(value, RoutingContext(query_scope=SCOPE), project=project), 'new-project')
    value = backend.get('info-0')
    execute(executor.preview_link(value, RoutingContext(query_scope=SCOPE, already_stored=True,
        selected_project='project', existing_dossier='project'), project_revision=executor.storage.get('project').revision), 'link-existing')
    value = backend.get('info-1')
    execute(executor.preview_information(replace(value, content='Synthetic corrected measurement'),
        RoutingContext(query_scope=SCOPE, update_target=TargetRevision(value.information_id, value.revision))), 'update-information')
    assert backend.get('info-1').revision == 2

    # A durable parent interruption is recovered by the actual global dispatcher.
    value = memory('interrupted', scheduled=True)
    prepared = executor.preview_information(value, RoutingContext(query_scope=SCOPE))
    def stop(stage):
        if stage == 'after_information':
            raise RuntimeError('synthetic interruption after durable Information publication')
    executor._checkpoint = stop
    try:
        execute(prepared, 'interrupted-route')
    except RuntimeError:
        pass
    else:
        raise AssertionError('expected injected interruption')
    executor._checkpoint = lambda stage: None
    assert not check_readiness(root)['ready']
    recovery = recover_all(root)
    assert recovery['readiness']['ready']
    execute(prepared, 'interrupted-route')
    assert backend.get('interrupted').revision == 1

    threads = ThreadService.for_backend(backend)
    current = threads.get('project')
    threads.update_thread('project', {'kind': 'ADD_ACTION', 'action': {'action_id': 'measure',
        'description': 'Synthetic measurement', 'status': 'PLANNED', 'metadata': {}}},
        previous_revision=current.revision, operation_id='project-action', event_id='project-action-event',
        actor='synthetic-human', timestamp=STAMP)
    disposable = Thread('deleted-project', 'Disposable', 'Synthetic deletion', created_at=STAMP, updated_at=STAMP)
    threads.create_linked(disposable, 'info-2', operation_id='temporary-project', event_id='temporary-project-event')
    threads.delete('deleted-project', previous_revision=1, operation_id='delete-project')
    assert threads.get('deleted-project') is None

    backend.delete_request('info-8', 'synthetic-human', 'Synthetic cancellation', 1, 'cancel-information')
    backend.cancel_delete('info-8', 'cancel-information')
    FilesystemInformationWrites(backend).compact(executor.child_id('store-7', 'information'))
    backend.delete_request('info-7', 'synthetic-human', 'Synthetic approved deletion', 1, 'delete-information')
    backend.approve_delete('info-7', 'delete-information')
    assert backend.get('info-7') is None and backend.get('info-8').revision == 1
    notes_before = 'Synthetic human notes before\r\n'
    notes_after = '\r\nSynthetic human notes after\r\n'
    snapshot = executor.dossiers.read_notes('project')
    note_edit = executor.dossiers.replace_notes('project', before=notes_before, after=notes_after,
        expected_document_sha256=snapshot['document_sha256'])
    assert note_edit['status'] == 'UPDATED'
    try:
        executor.dossiers.replace_notes('project', before='Stale editor overwrite', after='',
            expected_document_sha256=snapshot['document_sha256'])
    except DossierConflict:
        pass
    else:
        raise AssertionError('stale notes editor overwrote the current human notes')
    maintenance = MaintenancePass(root).run(at=DUE, query_scope=SCOPE)
    assert maintenance['status'] == 'COMPLETED', maintenance
    notes = executor.dossiers.read_notes('project')
    assert notes['before'] == notes_before and notes['after'] == notes_after
    lifecycle = LifecycleTriggers(backend)
    assert len(lifecycle.journal.ids()) == 5
    assert all(lifecycle.journal.read(identity)['status'] == 'COMPLETED' for identity in lifecycle.journal.ids())
    assert all(lifecycle.journal.read(identity)['result']['reason'] == 'RECHECK' for identity in lifecycle.journal.ids())
    writer = FilesystemInformationWrites(backend)
    # Retain one full journal alongside compact receipts for mixed-format audits.
    kept_live = executor.child_id('update-information', 'information')
    compact = writer.compact_batch([identity for identity in writer.journal.ids() if identity != kept_live])
    assert compact['status'] == 'COMPLETED', compact
    assert check_readiness(root)['ready']
    payload = executor.recall_payload('measurement', query_scope=SCOPE, at=DUE,
        project_id='project', max_payload_chars=8000, prefix='Synthetic sources:\n', suffix='\nReview uncertainty.')
    recalled = json.loads(payload.text[len('Synthetic sources:\n'):-len('\nReview uncertainty.')])
    assert recalled['dossier_status'] == 'CURRENT' and recalled['items']
    assert all(item['needs_review'] and item['epistemic_status'] == 'UNVERIFIED' for item in recalled['items'])
    assert payload.payload_chars <= 8000
    assert notes_before.strip() not in payload.text and notes_after.strip() not in payload.text
    # Original routing receipt remains replayable after compaction and deletion.
    deleted_receipt = executor.journal.read('store-7')
    assert deleted_receipt['status'] == 'COMMITTED' and backend.get('info-7') is None
    return dict(status='OK', synthetic=True, root=str(root), original_information_count=12,
                remaining_information_count=11, active_project_count=1, deleted_project_count=1,
                routing_receipts=len(executor.journal.ids()), completed_triggers=5,
                recovered_interruption=True, human_notes_preserved=True, stale_note_editor_refused=True,
                human_notes_not_ingested=True, human_note_edit=note_edit,
                retained_live_information_write=kept_live,
                compacted_information_writes=compact,
                recall_payload=asdict(payload), readiness=check_readiness(root),
                limitation='Synthetic only; no real user corpus, active service or power cut tested')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--report', type=Path, required=True, help='Separate output path outside scenario root')
    args = parser.parse_args(argv)
    root, report = args.root.absolute(), args.report.absolute()
    if root == report or root in report.parents or report.exists():
        parser.error('report must be a new file outside the disposable source root')
    result = run(root)
    result['tool_sha256'] = sha256(Path(__file__).read_bytes()).hexdigest()
    report.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + '\n')
    print(json.dumps({key: result[key] for key in ('status','synthetic','root','routing_receipts','completed_triggers')}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
