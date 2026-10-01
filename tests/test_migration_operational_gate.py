"""A mixed source must never produce a deceptively usable migration target."""
from pathlib import Path
import json
import shutil

import pytest

from core.backend.filesystem import FilesystemBackend
from core.backend.models import Memory
from core.information.writes import FilesystemInformationWrites
from core.migration.converter import convert, main
from tests.test_migration_converter import fingerprints
from tools.generate_scenario import generate


@pytest.mark.parametrize('status', ['PENDING_DELETE', 'APPLYING_DELETE', 'DELETED', 'CANCELLED'])
def test_operational_deletion_state_blocks_before_any_destination_write(tmp_path, status):
    generate(tmp_path / 'fixture', count=50)
    source = tmp_path / 'fixture/legacy'
    producer = FilesystemBackend(tmp_path / 'producer/persistent', tmp_path / 'producer/history')
    producer.store(Memory('reserved', content='private'))
    producer.delete_request('reserved', 'test', 'synthetic', 1, 'delete-reserved')
    if status == 'DELETED':
        producer.approve_delete('reserved', 'delete-reserved')
    record = json.loads((producer.pending_delete_root / 'reserved.json').read_text())
    record['status'] = status
    receipt = source / 'memory/history/pending-delete/reserved.json'
    receipt.parent.mkdir(parents=True)
    receipt.write_text(json.dumps(record))
    original = fingerprints(source)
    destination = tmp_path / 'target'

    report = convert(source, destination)

    assert report['converted'] == 0
    assert report['rejected'][0]['file'] == 'memory/history/pending-delete/reserved.json'
    assert report['rejected'][0]['reason'] == 'operational_state_requires_import_policy'
    assert not destination.exists()
    assert fingerprints(source) == original


@pytest.mark.parametrize('relative', [
    'operations/thread-create-v1/op.json', 'operations/thread-status-v1/op.json',
    'operations/thread-delete-v1/op.json', 'operations/information-write-v1/op.json',
    'operations/future-v99/op.json', 'operation-receipts/future-v99/op.json',
])
def test_any_operational_family_is_rejected_even_if_corrupt_or_unknown(tmp_path, relative):
    source = tmp_path / 'source'
    (source / 'memory/persistent').mkdir(parents=True)
    path = source / 'memory/history' / relative
    path.parent.mkdir(parents=True)
    path.write_text('{broken')
    destination = tmp_path / 'existing'
    destination.mkdir()
    (destination / 'keep').write_text('untouched')
    before = fingerprints(destination)
    report = convert(source, destination)
    assert report['converted'] == 0 and report['rejected']
    assert fingerprints(destination) == before


def test_compacted_receipt_blocks_cli_without_creating_destination(tmp_path, capsys):
    source = tmp_path / 'source'
    (source / 'memory/persistent').mkdir(parents=True)
    backend = FilesystemBackend(tmp_path / 'producer/persistent', tmp_path / 'producer/history')
    writer = FilesystemInformationWrites(backend)
    writer.create(Memory('info', content='data'), operation_id='op', event_id='event',
                  actor='test', timestamp='2026-10-01T00:00:00Z')
    writer.compact('op')
    shutil.copytree(backend.history_root / 'operation-receipts', source / 'memory/history/operation-receipts')
    destination = tmp_path / 'target'
    assert main(['--source', str(source), '--destination', str(destination)]) == 1
    assert json.loads(capsys.readouterr().out)['rejected']
    assert not destination.exists()


def test_gate_does_not_follow_linked_operational_directory(tmp_path):
    source = tmp_path / 'source'
    (source / 'memory/persistent').mkdir(parents=True)
    (source / 'memory/history').mkdir()
    outside = tmp_path / 'outside'
    outside.mkdir()
    (outside / 'secret').write_text('not part of migration')
    (source / 'memory/history/operations').symlink_to(outside, target_is_directory=True)
    report = convert(source, tmp_path / 'target')
    assert report['rejected'][0]['file'] == 'memory/history/operations'
    assert not (tmp_path / 'target').exists()
