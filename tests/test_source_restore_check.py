"""Restoration must preserve frozen source data and durable write receipts."""
import tarfile
import pytest
from tools.check_source_restore import run


def test_restore_replays_live_and_deleted_details_without_writes(tmp_path):
    report = run(temp_parent=tmp_path)
    assert report['status'] == 'PASS'
    assert report['exact_reference'] and report['extraction_preserved']
    assert report['deletion_preserved'] and report['replay_unchanged']
    assert report['audit_issues'] == 0 and report['compacted_write_receipts'] == 2
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize('lost', ['extraction.json', '/original', 'operation-receipts/information-write-v1/'])
def test_incomplete_archive_is_rejected_before_replay(tmp_path, monkeypatch, lost):
    original = tarfile.TarFile.add
    def omit(self, *args, **kwargs):
        kwargs['filter'] = lambda member: None if lost in member.name else member
        return original(self, *args, **kwargs)
    monkeypatch.setattr(tarfile.TarFile, 'add', omit)
    with pytest.raises(RuntimeError, match='restored file manifest differs'):
        run(temp_parent=tmp_path)
    assert list(tmp_path.iterdir()) == []
