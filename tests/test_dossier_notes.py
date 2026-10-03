"""Human notes are explicit noncanonical text with whole-document CAS."""
from hashlib import sha256
from pathlib import Path
import json,subprocess,sys
import pytest

from core.dossiers.projects import BEGIN,END,DossierConflict,ProjectDossiers
from core.dossiers.cli import main
from tests.test_routing_execution import seed,preview,execute
from tests.test_migration_converter import fingerprints


def fixture(root):
    backend,executor,memory=seed(root)
    execute(executor,preview(executor,memory))
    return backend,executor,executor.dossiers


def test_read_notes_is_a_byte_preserving_read_only_snapshot(tmp_path):
    backend,executor,dossiers=fixture(tmp_path)
    path=dossiers._path('project');before='Avant\r\n';after='\r\nAprès mémorisé\r\n'
    _,generated,_=dossiers._parts(dossiers._read_text(path))
    path.write_bytes((before+generated+after).encode())
    original=fingerprints(tmp_path)
    result=dossiers.read_notes('project')
    assert result['before']==before and result['after']==after
    assert result['document_sha256']==sha256(path.read_bytes()).hexdigest()
    assert result['canonical_ingestion'] is False and fingerprints(tmp_path)==original


def test_replace_notes_changes_only_human_sections_and_survives_rebuild(tmp_path):
    backend,executor,dossiers=fixture(tmp_path)
    path=dossiers._path('project');_,generated,_=dossiers._parts(dossiers._read_text(path))
    snapshot=dossiers.read_notes('project');original=fingerprints(tmp_path/'memory/persistent'),fingerprints(tmp_path/'memory/history')
    result=dossiers.replace_notes('project',before='Human before\r\n',after='\r\nHuman after\r\n',expected_document_sha256=snapshot['document_sha256'])
    assert result['status']=='UPDATED' and result['canonical_ingestion'] is False
    assert dossiers._read_text(path)=='Human before\r\n'+generated+'\r\nHuman after\r\n'
    assert result['document_sha256']==sha256(path.read_bytes()).hexdigest()
    assert (fingerprints(tmp_path/'memory/persistent'),fingerprints(tmp_path/'memory/history'))==original
    assert dossiers.rebuild('project')['status']=='UNCHANGED'
    assert dossiers.read_notes('project')['before']=='Human before\r\n'
    assert dossiers.status('project')['status']=='CURRENT'


def test_same_notes_under_current_snapshot_are_unchanged(tmp_path):
    _,_,dossiers=fixture(tmp_path);snapshot=dossiers.read_notes('project');before=fingerprints(tmp_path)
    result=dossiers.replace_notes('project',before=snapshot['before'],after=snapshot['after'],expected_document_sha256=snapshot['document_sha256'])
    assert result['status']=='UNCHANGED' and fingerprints(tmp_path)==before


def test_second_editor_with_old_snapshot_cannot_overwrite_first(tmp_path):
    _,_,dossiers=fixture(tmp_path);snapshot=dossiers.read_notes('project')
    dossiers.replace_notes('project',before='First\n',after='\n',expected_document_sha256=snapshot['document_sha256'])
    before=fingerprints(tmp_path)
    with pytest.raises(DossierConflict):dossiers.replace_notes('project',before='Second\n',after='\n',expected_document_sha256=snapshot['document_sha256'])
    assert dossiers.read_notes('project')['before']=='First\n' and fingerprints(tmp_path)==before


def test_rebuilt_generated_body_invalidates_whole_document_snapshot(tmp_path):
    backend,executor,dossiers=fixture(tmp_path);snapshot=dossiers.read_notes('project')
    from dataclasses import replace
    from core.information.writes import FilesystemInformationWrites
    current=backend.get('second')
    FilesystemInformationWrites(backend).update(replace(current,content='Changed'),previous_revision=current.revision,
        operation_id='changed',event_id='changed-event',actor='human',timestamp='2026-10-03T01:30:00Z')
    dossiers.rebuild('project');before=fingerprints(tmp_path)
    with pytest.raises(DossierConflict):dossiers.replace_notes('project',before='Old editor\n',after='\n',expected_document_sha256=snapshot['document_sha256'])
    assert fingerprints(tmp_path)==before


@pytest.mark.parametrize('before,after',[(BEGIN,''),('',END),(END,''),('',BEGIN),(None,''),('',1)])
def test_invalid_or_boundary_injecting_notes_are_refused_without_change(tmp_path,before,after):
    _,_,dossiers=fixture(tmp_path);snapshot=dossiers.read_notes('project');original=fingerprints(tmp_path)
    with pytest.raises((ValueError,DossierConflict)):dossiers.replace_notes('project',before=before,after=after,expected_document_sha256=snapshot['document_sha256'])
    assert fingerprints(tmp_path)==original


@pytest.mark.parametrize('digest',[None,'short','g'*64,True])
def test_invalid_document_digest_is_refused(tmp_path,digest):
    _,_,dossiers=fixture(tmp_path);before=fingerprints(tmp_path)
    with pytest.raises((ValueError,DossierConflict)):dossiers.replace_notes('project',before='Notes',after='',expected_document_sha256=digest)
    assert fingerprints(tmp_path)==before


def test_missing_document_is_not_created_by_notes_commands(tmp_path):
    _,_,dossiers=fixture(tmp_path);path=dossiers._path('project');path.unlink();original=fingerprints(tmp_path)
    with pytest.raises(DossierConflict):dossiers.read_notes('project')
    with pytest.raises(DossierConflict):dossiers.replace_notes('project',before='Notes',after='',expected_document_sha256='0'*64)
    assert fingerprints(tmp_path)==original


def test_malformed_generated_boundaries_require_review_before_editing(tmp_path):
    _,_,dossiers=fixture(tmp_path);path=dossiers._path('project');path.write_text('Human notes without generated markers')
    before=fingerprints(tmp_path)
    with pytest.raises(DossierConflict):dossiers.replace_notes('project',before='Replacement',after='',expected_document_sha256=sha256(path.read_bytes()).hexdigest())
    assert fingerprints(tmp_path)==before


def test_global_pending_or_unknown_history_blocks_note_publication(tmp_path):
    backend,_,dossiers=fixture(tmp_path);snapshot=dossiers.read_notes('project')
    path=backend.history_root/'operations/unknown/entry.json';path.parent.mkdir(parents=True);path.write_text('{}')
    before=fingerprints(tmp_path)
    with pytest.raises(DossierConflict):dossiers.replace_notes('project',before='Replacement',after='',expected_document_sha256=snapshot['document_sha256'])
    assert fingerprints(tmp_path)==before
    assert dossiers.read_notes('project')['document_sha256']==snapshot['document_sha256']


def test_atomic_publication_failure_keeps_original_notes(tmp_path,monkeypatch):
    _,_,dossiers=fixture(tmp_path);snapshot=dossiers.read_notes('project');before=fingerprints(tmp_path)
    def fail(*args,**kwargs):raise OSError('publication refused')
    monkeypatch.setattr('core.dossiers.projects.atomic_write_text',fail)
    with pytest.raises(OSError):dossiers.replace_notes('project',before='Replacement',after='',expected_document_sha256=snapshot['document_sha256'])
    assert fingerprints(tmp_path)==before


def test_cli_notes_read_edit_and_stale_refusal(tmp_path,capsys):
    _,_,dossiers=fixture(tmp_path)
    assert main(['--root',str(tmp_path),'notes','project'])==0
    snapshot=json.loads(capsys.readouterr().out)
    document=tmp_path/'notes.json';document.write_text(json.dumps({'before':'Human before\r\n','after':'\nHuman after'}))
    argv=['--root',str(tmp_path),'edit-notes','project','--notes',str(document),'--expected-document-sha256',snapshot['document_sha256']]
    assert main(argv)==0 and json.loads(capsys.readouterr().out)['status']=='UPDATED'
    assert main(argv)==1 and json.loads(capsys.readouterr().out)['status']=='BLOCKED'
    assert dossiers.read_notes('project')['before']=='Human before\r\n'


def test_two_process_editors_allow_one_snapshot_owner(tmp_path):
    _,_,dossiers=fixture(tmp_path);snapshot=dossiers.read_notes('project')
    script='''
import sys,json
from pathlib import Path
from core.backend.filesystem import FilesystemBackend
from core.threads.storage import ThreadStorage
from core.dossiers.projects import ProjectDossiers,DossierConflict
root=Path(sys.argv[1]);backend=FilesystemBackend(root/'memory/persistent',root/'memory/history')
dossiers=ProjectDossiers(backend,ThreadStorage(backend.persistent_root),root/'memory/dossiers')
try:
 result=dossiers.replace_notes('project',before=sys.argv[3],after='\\n',expected_document_sha256=sys.argv[2])
 print(result['status'])
except DossierConflict:
 print('BLOCKED')
'''
    processes=[subprocess.Popen([sys.executable,'-B','-c',script,str(tmp_path),snapshot['document_sha256'],name],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True) for name in ['Editor one','Editor two']]
    replies=[process.communicate(timeout=15) for process in processes]
    assert all(process.returncode==0 for process in processes),replies
    assert sorted(reply[0].strip() for reply in replies)==['BLOCKED','UPDATED']
    assert dossiers.read_notes('project')['before'] in {'Editor one','Editor two'}


def test_note_edit_on_stale_view_does_not_refresh_generated_source(tmp_path):
    backend,_,dossiers=fixture(tmp_path);snapshot=dossiers.read_notes('project')
    from dataclasses import replace
    from core.information.writes import FilesystemInformationWrites
    current=backend.get('second')
    FilesystemInformationWrites(backend).update(replace(current,content='Canonically changed'),previous_revision=1,
        operation_id='changed',event_id='changed-event',actor='human',timestamp='2026-10-03T01:30:00Z')
    assert dossiers.status('project')['status']=='STALE'
    result=dossiers.replace_notes('project',before='Human comment\n',after='\n',expected_document_sha256=snapshot['document_sha256'])
    assert result['status']=='UPDATED' and dossiers.status('project')['status']=='STALE'
    assert 'Canonically changed' not in dossiers._read_text(dossiers._path('project'))
    dossiers.rebuild('project')
    assert dossiers.status('project')['status']=='CURRENT' and dossiers.read_notes('project')['before']=='Human comment\n'


def test_orphan_human_notes_are_editable_without_recreating_deleted_project(tmp_path):
    backend,executor,dossiers=fixture(tmp_path)
    from core.threads.service import ThreadService
    ThreadService.for_backend(backend).delete('project',previous_revision=executor.storage.get('project').revision,operation_id='delete-project')
    dossiers.rebuild('project');snapshot=dossiers.read_notes('project')
    result=dossiers.replace_notes('project',before='Preserved orphan notes\n',after='\n',expected_document_sha256=snapshot['document_sha256'])
    assert result['status']=='UPDATED' and executor.storage.get('project') is None
    assert dossiers.read_notes('project')['before']=='Preserved orphan notes\n'
    assert dossiers.rebuild('project')['status']=='UNCHANGED'


def test_cli_note_reader_on_absent_root_does_not_initialize(tmp_path,capsys):
    root=tmp_path/'absent'
    assert main(['--root',str(root),'notes','project'])==1
    assert json.loads(capsys.readouterr().out)['status']=='BLOCKED' and not root.exists()


def test_lost_acknowledgement_after_atomic_notes_publication_is_inspectable(tmp_path):
    _,_,dossiers=fixture(tmp_path);snapshot=dossiers.read_notes('project')
    generated=dossiers._parts(dossiers._read_text(dossiers._path('project')))[1]
    script='''
import os,sys
from pathlib import Path
from core.backend.filesystem import FilesystemBackend
from core.threads.storage import ThreadStorage
from core.dossiers.projects import ProjectDossiers
import core.dossiers.projects as module
root=Path(sys.argv[1]);backend=FilesystemBackend(root/'memory/persistent',root/'memory/history')
dossiers=ProjectDossiers(backend,ThreadStorage(backend.persistent_root),root/'memory/dossiers')
original=module.atomic_write_text
def stop(*args,**kwargs):
 original(*args,**kwargs)
 os._exit(74)
module.atomic_write_text=stop
dossiers.replace_notes('project',before='Published before lost reply\\r\\n',after='\\r\\nComplete notes',expected_document_sha256=sys.argv[2])
'''
    process=subprocess.run([sys.executable,'-B','-c',script,str(tmp_path),snapshot['document_sha256']])
    assert process.returncode==74
    current=dossiers.read_notes('project')
    assert current['before']=='Published before lost reply\r\n' and current['after']=='\r\nComplete notes'
    assert dossiers._parts(dossiers._read_text(dossiers._path('project')))[1]==generated
    with pytest.raises(DossierConflict):dossiers.replace_notes('project',before=current['before'],after=current['after'],expected_document_sha256=snapshot['document_sha256'])
    assert dossiers.replace_notes('project',before=current['before'],after=current['after'],expected_document_sha256=current['document_sha256'])['status']=='UNCHANGED'
