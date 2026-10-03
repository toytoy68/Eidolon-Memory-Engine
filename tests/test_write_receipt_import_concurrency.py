"""An unlocked audit must not reject a cooperative Information receipt publication."""
import os
import threading
import pytest

from core.migration.write_receipts import import_write_receipts
from core.operations.readiness import check_readiness
from core.persistence import exclusive_write
from tests.test_write_receipt_import import seed
from tests.test_migration_converter import fingerprints


@pytest.mark.parametrize('family',['events/information-write-v1','operation-receipts/information-write-v1'])
def test_importer_waits_for_temporary_event_then_replays(tmp_path,monkeypatch,family):
    source,destination,_,_=seed(tmp_path)
    reached,release=threading.Event(),threading.Event()
    real=os.replace;results={};used=False
    def pause(src,dst):
        nonlocal used
        if not used and family in str(dst):
            used=True;reached.set()
            assert release.wait(15)
        return real(src,dst)
    monkeypatch.setattr(os,'replace',pause)
    def run(key):results[key]=import_write_receipts(source,destination)
    first=threading.Thread(target=run,args=('first',));second=threading.Thread(target=run,args=('second',))
    first.start()
    try:
        assert reached.wait(5)
        assert not check_readiness(destination)['ready']
        second.start();second.join(0.3)
        waited=second.is_alive()
    finally:
        release.set();first.join(10)
        if second.ident is not None:second.join(10)
    assert waited
    assert results['first']['status']=='IMPORTED'
    assert results['second']['status']=='UNCHANGED'
    assert check_readiness(destination)['ready']


def test_abandoned_temp_remains_blocked_without_publication(tmp_path):
    source,destination,_,dst=seed(tmp_path)
    with exclusive_write(dst.backend.persistent_root), exclusive_write(dst.events.events_root), exclusive_write(dst.operations.root):pass
    (dst.events.events_root/'.abandoned').write_text('{')
    before=fingerprints(destination)
    result=import_write_receipts(source,destination)
    assert result['status']=='BLOCKED' and not result['imported']
    assert fingerprints(destination)==before


def test_unlocked_invalid_destination_is_not_mutated(tmp_path):
    source,destination,_,dst=seed(tmp_path)
    (dst.backend.persistent_root/'.write.lock').unlink()  # stopped test tree, never-locked scenario
    (dst.events.events_root/'.abandoned').write_text('{')
    before=fingerprints(destination)
    assert import_write_receipts(source,destination)['status']=='BLOCKED'
    assert fingerprints(destination)==before


def test_invalid_source_does_not_wait_for_destination_lock(tmp_path):
    source,destination,src,dst=seed(tmp_path)
    (src.events.events_root/'.abandoned').write_text('{')
    holding,release=threading.Event(),threading.Event();results={}
    def hold():
        with exclusive_write(dst.backend.persistent_root):
            holding.set();release.wait(15)
    holder=threading.Thread(target=hold);holder.start()
    assert holding.wait(5)
    worker=threading.Thread(target=lambda:results.setdefault('result',import_write_receipts(source,destination)))
    try:
        worker.start();worker.join(2)
        immediate=not worker.is_alive()
    finally:
        release.set();holder.join(5);worker.join(5)
    assert immediate and results['result']['status']=='BLOCKED'
