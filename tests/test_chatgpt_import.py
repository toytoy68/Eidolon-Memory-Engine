import json
import pytest
from core.sources.chatgpt_import import import_exports, plan_conversation
from core.operations.readiness import check_readiness
from core.backend.filesystem import FilesystemBackend


def conversation(text='hello'):
    return dict(id='conversation-1', create_time=1700000000, title='test', current_node='b', mapping={
        'a': dict(parent=None, message=dict(id='a', author={'role':'user'}, create_time=1700000000,
            content={'content_type':'text','parts':[text]})),
        'b': dict(parent='a', message=dict(id='b', author={'role':'assistant'}, create_time=1700000001,
            content={'content_type':'text','parts':['proposal']})),
        'c': dict(parent='a', message=dict(id='c', author={'role':'assistant'}, channel='analysis',
            content={'content_type':'text','parts':['internal']}))})


def test_archive_retains_roles_dates_links_and_excludes_analysis():
    memory, at=plan_conversation(conversation(),'hash')
    data=json.loads(memory.content)
    assert [m['role'] for m in data['messages']]==['user','assistant']
    assert data['messages'][1]['parent']=='a'
    assert 'internal' not in memory.content
    assert memory.metadata['epistemic_status']=='UNVERIFIED'
    assert memory.temporal['observed_at']==at


def test_import_replays_without_duplicates_and_preserves_original(tmp_path):
    file=tmp_path/'01.json';raw=json.dumps([conversation()]).encode();file.write_bytes(raw)
    root=tmp_path/'corpus'
    assert import_exports(root,[file])['conversations']==1
    backend=FilesystemBackend(root/'memory/persistent',root/'memory/history')
    identity=plan_conversation(conversation(), 'hash')[0].information_id
    before=backend.get(identity)
    import_exports(root,[file])
    assert backend.get(identity)==before
    assert len(list((root/'memory/persistent').glob('*.md')))==1
    assert next((root/'import-originals').glob('*.json')).read_bytes()==raw
    assert check_readiness(root)['ready']


def test_conflicting_versions_rejected_before_writing(tmp_path):
    file=tmp_path/'01.json';file.write_text(json.dumps([conversation(),conversation('changed')]))
    root=tmp_path/'corpus'
    with pytest.raises(ValueError,match='conflicting'):
        import_exports(root,[file])
    assert not root.exists()


def test_non_test_root_refused(tmp_path):
    file=tmp_path/'01.json';file.write_text(json.dumps([conversation()]))
    root=tmp_path/'active';root.mkdir();(root/'existing').write_text('keep')
    with pytest.raises(ValueError,match='nonempty'):
        import_exports(root,[file])
    assert (root/'existing').read_text()=='keep'
