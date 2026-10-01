from dataclasses import replace
import json

import pytest

from core.backend.filesystem import FilesystemBackend
from core.backend.models import Memory
from core.backend.errors import InformationDeletionBlocked
from core.information.writes import FilesystemInformationWrites
from core.information.write_audit import audit_information_writes
from core.operations.errors import OperationConflict
from tools.vm_acceptance import hashes


def setup(tmp_path):
    writer = FilesystemInformationWrites(FilesystemBackend(tmp_path / 'memory/persistent', tmp_path / 'memory/history'))
    memory = Memory('info-1', content='A short private secret', metadata={'epistemic_status': 'CONFIRMED', 'extension': {'text': 'also private'}})
    args = dict(operation_id='create', event_id='created', actor='human', timestamp='fixed')
    result = writer.create(memory, **args)
    return writer, memory, args, result


def test_compact_then_edit_delete_and_replay_without_resurrection(tmp_path):
    writer, memory, args, result = setup(tmp_path)
    assert writer.compact('create') == result
    assert not writer.operations._path('create').exists()
    receipt = writer.journal.receipt_path('create').read_text()
    assert memory.content not in receipt and 'also private' not in receipt
    assert json.loads(receipt)['format_version'] == 1
    writer.update(replace(memory, content='new'), previous_revision=1,
                  **(args | {'operation_id': 'update', 'event_id': 'updated'}))
    writer.backend.delete_request('info-1', 'human', 'obsolete', 2, 'delete')
    with pytest.raises(InformationDeletionBlocked, match='compact'):
        writer.backend.approve_delete('info-1', 'delete')
    writer.compact('update')
    writer.backend.approve_delete('info-1', 'delete')
    before = hashes(tmp_path)
    assert writer.create(memory, **args) == result
    assert hashes(tmp_path) == before
    assert writer.backend.get('info-1') is None
    with pytest.raises(OperationConflict, match='different command'):
        writer.create(replace(memory, content='different'), **args)


@pytest.mark.parametrize('phase', ['published', 'removed'])
def test_compaction_interruption_and_common_readers(tmp_path, monkeypatch, phase):
    import core.information.compaction as compact
    writer, memory, args, result = setup(tmp_path)
    name = 'atomic_write_text' if phase == 'published' else 'durable_unlink'
    real = getattr(compact, name)
    def interrupted(*a, **kw):
        real(*a, **kw)
        raise RuntimeError('interrupted')
    monkeypatch.setattr(compact, name, interrupted)
    with pytest.raises(RuntimeError):
        writer.compact('create')
    snapshot = hashes(tmp_path)
    audit = audit_information_writes(tmp_path)
    assert hashes(tmp_path) == snapshot  # Audits must not create locks/directories.
    assert audit['records']['create']['status'] == ('COMPACTING' if phase == 'published' else 'COMPACTED')
    assert writer.create(memory, **args) == result
    monkeypatch.setattr(compact, name, real)
    assert writer.recover()['create']['status'] == 'COMMITTED'
    assert not writer.operations._path('create').exists()
    assert audit_information_writes(tmp_path)['records']['create']['status'] == 'COMPACTED'


def test_divergent_receipt_blocks_replay_recovery_inventory_and_deletion(tmp_path, monkeypatch):
    import core.information.compaction as compact
    from core.migration.inventory import inventory
    writer, memory, args, result = setup(tmp_path)
    monkeypatch.setattr(compact, 'durable_unlink', lambda path: (_ for _ in ()).throw(RuntimeError()))
    with pytest.raises(RuntimeError):
        writer.compact('create')
    path = writer.journal.receipt_path('create')
    data = json.loads(path.read_text())
    data['command_fingerprint'] = '0' * 64
    path.write_text(json.dumps(data))
    before = hashes(tmp_path)
    with pytest.raises(OperationConflict, match='diverg'):
        writer.create(memory, **args)
    assert writer.recover()['create']['status'] == 'BLOCKED'
    assert audit_information_writes(tmp_path)['issues']
    assert inventory(tmp_path)['needs_review']
    with pytest.raises(InformationDeletionBlocked):
        writer.backend.delete_request('info-1', 'human', 'obsolete', 1, 'delete')
    assert hashes(tmp_path) == before


def test_compaction_requires_matching_event_and_no_pending_operation(tmp_path, monkeypatch):
    writer, memory, args, result = setup(tmp_path)
    event = writer.events._path('created')
    content = event.read_text()
    event.unlink()
    with pytest.raises(OperationConflict, match='Event'):
        writer.compact('create')
    assert writer.operations._path('create').exists()
    event.write_text(content)
    original = writer.operations.create
    def stop(op):
        original(op)
        raise RuntimeError()
    monkeypatch.setattr(writer.operations, 'create', stop)
    with pytest.raises(RuntimeError):
        writer.update(memory, previous_revision=1, **(args | {'operation_id': 'update', 'event_id': 'updated'}))
    with pytest.raises(OperationConflict, match='pending'):
        writer.compact('create')
    with pytest.raises(OperationConflict, match='COMMITTED'):
        writer.compact('update')


def test_read_only_audit_empty_root_creates_nothing(tmp_path):
    before = hashes(tmp_path)
    assert audit_information_writes(tmp_path) == {'records': {}, 'issues': []}
    assert hashes(tmp_path) == before
    assert list(tmp_path.iterdir()) == []


def test_compact_receipt_rejects_unknown_version_and_inconsistent_result(tmp_path):
    writer, memory, args, result = setup(tmp_path)
    writer.compact('create')
    path = writer.journal.receipt_path('create')
    saved = json.loads(path.read_text())
    for modified in [saved | {'format_version': 2}, saved | {'result': result | {'revision': 99}}]:
        path.write_text(json.dumps(modified))
        with pytest.raises(OperationConflict):
            writer.create(memory, **args)
        assert audit_information_writes(tmp_path)['issues']
    path.write_text(json.dumps(saved))
    assert writer.create(memory, **args) == result


def test_publication_is_reread_before_retiring_plan(tmp_path, monkeypatch):
    import core.information.compaction as compact
    writer, memory, args, result = setup(tmp_path)
    real = compact.atomic_write_text
    def corrupted_publication(path, text):
        data = json.loads(text)
        data['plan_hash'] = 'f' * 64
        real(path, json.dumps(data))
    monkeypatch.setattr(compact, 'atomic_write_text', corrupted_publication)
    with pytest.raises(OperationConflict, match='divergent'):
        writer.compact('create')
    assert writer.operations._path('create').exists()


def test_receipt_still_reserves_event_id_when_event_file_is_missing(tmp_path):
    writer, memory, args, result = setup(tmp_path)
    writer.compact('create')
    writer.events._path('created').unlink()
    with pytest.raises(OperationConflict, match='reserved'):
        writer.create(replace(memory, information_id='info-2'), **(args | {'operation_id': 'different'}))
    assert writer.backend.get('info-2') is None
    assert audit_information_writes(tmp_path)['issues']


def test_compaction_cli_and_inventory_do_not_lose_receipts(tmp_path):
    import os
    import subprocess
    import sys
    from core.migration.inventory import inventory
    writer, memory, args, result = setup(tmp_path)
    output = subprocess.run([sys.executable, '-B', '-m', 'core.information.cli', 'compact', 'create'],
                            env=dict(os.environ, MEMORY_ENGINE_ROOT=str(tmp_path)), capture_output=True, text=True)
    assert output.returncode == 0, output.stderr
    assert json.loads(output.stdout) == result
    before = hashes(tmp_path)
    report = inventory(tmp_path)
    assert report['categories']['information_write_receipts'] == {'core_information_receipt_v1': 1}
    assert report['information_writes']['records']['create']['status'] == 'COMPACTED'
    assert report['needs_review'] == []
    assert hashes(tmp_path) == before


def test_compaction_syncs_journal_directory_after_unlink(tmp_path, monkeypatch):
    import core.information.compaction as compact
    writer, memory, args, result = setup(tmp_path)
    real = compact.sync_directory
    calls = []
    def synced(path):
        calls.append((path, writer.operations._path('create').exists(), writer.journal.receipt_path('create').exists()))
        real(path)
    monkeypatch.setattr(compact, 'sync_directory', synced)
    writer.compact('create')
    assert calls[-1] == (writer.operations.root, False, True)
