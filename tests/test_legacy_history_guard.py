"""Deleting the final visible core object must never reopen legacy writes."""
import pytest
from core.migration.legacy_guard import require_legacy_persistent_only
from tests.test_information_writes import service,memory,command


def test_last_information_deleted_after_compaction_keeps_legacy_blocked(tmp_path):
    writer=service(tmp_path)
    writer.create(memory(),**command())
    writer.compact('create')
    writer.backend.delete_request('info-1','human','remove',1,'delete-last')
    writer.backend.approve_delete('info-1','delete-last')
    assert writer.backend.get('info-1') is None
    with pytest.raises(ValueError,match='core'):
        require_legacy_persistent_only(writer.backend.persistent_root,writer.backend.history_root)


@pytest.mark.parametrize('relative',[
    'operations/information-write-v1','operation-receipts/information-write-v1',
    'events/information-write-v1','operations/thread-delete-v1','events/thread-delete-v1',
    'pending-delete','events/lifecycle-trigger-v1',
])
def test_canonical_history_remains_a_legacy_boundary(tmp_path,relative):
    persistent=tmp_path/'persistent';persistent.mkdir()
    history=tmp_path/'history';directory=history/relative;directory.mkdir(parents=True)
    (directory/'retained.json').write_text('{}')
    with pytest.raises(ValueError,match='core'):
        require_legacy_persistent_only(persistent,history)


def test_empty_core_directories_and_lock_only_are_not_history(tmp_path):
    persistent=tmp_path/'persistent';persistent.mkdir()
    history=tmp_path/'history';directory=history/'operation-receipts/information-write-v1'
    directory.mkdir(parents=True);(directory/'.write.lock').touch()
    require_legacy_persistent_only(persistent,history)


def test_invalid_core_history_directory_is_blocked(tmp_path):
    persistent=tmp_path/'persistent';persistent.mkdir()
    history=tmp_path/'history';(history/'operations').mkdir(parents=True)
    (history/'operations/information-write-v1').write_text('unexpected')
    with pytest.raises(ValueError,match='core'):
        require_legacy_persistent_only(persistent,history)
