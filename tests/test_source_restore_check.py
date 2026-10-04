"""Restoration must preserve frozen source data and durable write receipts."""
import tarfile
import pytest
from tools.check_source_restore import run


def test_restore_replays_live_and_deleted_details_without_writes(tmp_path):
    report = run(temp_parent=tmp_path)
    assert report['status'] == 'PASS'
    assert report['exact_reference'] and report['extraction_preserved']
    assert report['extraction_commitment_preserved']
    assert report['deletion_preserved'] and report['replay_unchanged']
    assert report['audit_issues'] == 0 and report['compacted_write_receipts'] == 2
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize('lost', ['extraction.json', '/original', 'operation-receipts/information-write-v1/', 'source-extractions-v1/'])
def test_incomplete_archive_is_rejected_before_replay(tmp_path, monkeypatch, lost):
    original = tarfile.TarFile.add
    def omit(self, *args, **kwargs):
        kwargs['filter'] = lambda member: None if lost in member.name else member
        return original(self, *args, **kwargs)
    monkeypatch.setattr(tarfile.TarFile, 'add', omit)
    with pytest.raises(RuntimeError, match='restored file manifest differs'):
        run(temp_parent=tmp_path)
    assert list(tmp_path.iterdir()) == []


def test_pending_archive_stays_blocked_until_explicit_recovery(tmp_path):
    import multiprocessing
    if 'fork' not in multiprocessing.get_all_start_methods():
        pytest.skip('fork required')
    report = run(temp_parent=tmp_path, pending=True)
    assert report['status'] == 'PASS' and report['active_objects'] == 2
    assert report['restored_pending_operation'] and report['explicit_recovery_verified']
    assert report['source_unchanged'] and report['replay_unchanged']
    assert report['compacted_write_receipts'] == 2
    assert list(tmp_path.iterdir()) == []


def test_restore_does_not_claim_recovery_when_pending_journal_remains(tmp_path, monkeypatch):
    import multiprocessing
    from core.information.writes import FilesystemInformationWrites
    if 'fork' not in multiprocessing.get_all_start_methods():
        pytest.skip('fork required')
    monkeypatch.setattr(FilesystemInformationWrites, 'recover', lambda self: None)
    with pytest.raises(RuntimeError, match='explicit recovery left restored corpus blocked'):
        run(temp_parent=tmp_path, pending=True)
    assert list(tmp_path.iterdir()) == []
