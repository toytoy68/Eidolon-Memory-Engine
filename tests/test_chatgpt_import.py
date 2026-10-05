import json
import pytest
from core.sources.chatgpt_import import import_exports, plan_conversation
from core.operations.readiness import check_readiness
from core.backend.filesystem import FilesystemBackend
from core.sources.chatgpt_import import main


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


@pytest.mark.parametrize('parts', ['Bonjour', {'texte': 'Bonjour'}, None, 42, True])
def test_malformed_parts_blocks_entire_batch_before_destination(tmp_path, capsys, parts):
    bad = conversation()
    bad['id'] = 'malformed-conversation'
    bad['mapping']['a']['message']['content']['parts'] = parts
    source = tmp_path / 'invalid.json'
    source.write_text(json.dumps([conversation(), bad]), encoding='utf-8')
    root = tmp_path / 'corpus'
    with pytest.raises(ValueError, match='parts must be a list'):
        import_exports(root, [source])
    assert not root.exists()
    assert main(['--root', str(root), str(source)]) == 1
    result = json.loads(capsys.readouterr().out)
    assert result == {'status': 'BLOCKED', 'reason': 'conversation content.parts must be a list'}
    assert not root.exists()


def test_malformed_parts_preserves_existing_corpus(tmp_path):
    source = tmp_path / 'valid.json'
    source.write_text(json.dumps([conversation()]), encoding='utf-8')
    root = tmp_path / 'corpus'
    import_exports(root, [source])
    before = {str(p.relative_to(root)): p.read_bytes() for p in root.rglob('*') if p.is_file()}
    bad = conversation('different')
    bad['mapping']['a']['message']['content']['parts'] = {'text': 'hidden corruption'}
    source.write_text(json.dumps([bad]), encoding='utf-8')
    with pytest.raises(ValueError, match='parts must be a list'):
        import_exports(root, [source])
    assert before == {str(p.relative_to(root)): p.read_bytes() for p in root.rglob('*') if p.is_file()}


def test_multimodal_parts_keeps_text_and_ignores_nontext_objects():
    item = conversation()
    item['mapping']['a']['message']['content'] = {
        'content_type': 'multimodal_text',
        'parts': ['before', {'content_type': 'image_asset_pointer', 'asset_pointer': 'synthetic'}, 'after'],
    }
    memory, _ = plan_conversation(item, 'hash')
    assert json.loads(memory.content)['messages'][0]['content'] == 'before\nafter'
