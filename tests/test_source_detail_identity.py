"""Source details retain identity across analyses without rewriting v1 receipts."""
import pytest
from core.backend.filesystem import FilesystemBackend
from core.sources.validation import accept_detail
from tests.test_source_ai import setup, review
from tools.vm_acceptance import hashes


def backend(root):
    return FilesystemBackend(root/'memory/persistent',root/'memory/history')


@pytest.mark.parametrize('detail',['Lina vit à Lyon. ', 'Lina\tvit à Lyon.', 'Lina\u00a0vit à Lyon.', 'Lina vit à Lyon.'])
def test_whitespace_and_nfc_variants_reuse_first_validation(tmp_path,detail):
    _,record,extraction=setup(tmp_path);draft=review(record,extraction)
    first=accept_detail(tmp_path,draft,detail=draft['detail'],actor='human')
    before=hashes(tmp_path)
    assert accept_detail(tmp_path,draft,detail=detail,actor='human')==first
    assert hashes(tmp_path)==before


def test_new_analysis_actor_and_model_do_not_duplicate_source_detail(tmp_path):
    _,record,extraction=setup(tmp_path);draft=review(record,extraction)
    first=accept_detail(tmp_path,draft,detail=draft['detail'],actor='human')
    newer=dict(draft,model='other',model_digest='b'*64,proposed_at='2026-10-04T00:00:00Z',detail='New suggestion')
    before=hashes(tmp_path)
    assert accept_detail(tmp_path,newer,detail=draft['detail'],actor='other-human')==first
    assert hashes(tmp_path)==before
    assert backend(tmp_path).get(first['information_id']).provenance['validated_by']=='human'


@pytest.mark.parametrize('detail',['lina vit à Lyon.','Lina vit a Lyon.','Lina vit à Lyon!','Lina vit à Paris.'])
def test_meaningful_text_changes_remain_distinct(tmp_path,detail):
    _,record,extraction=setup(tmp_path);draft=review(record,extraction)
    first=accept_detail(tmp_path,draft,detail=draft['detail'],actor='human')
    second=accept_detail(tmp_path,draft,detail=detail,actor='human')
    assert first['information_id']!=second['information_id']


def test_variant_replay_after_compaction_and_deletion_never_resurrects(tmp_path):
    from core.information.writes import FilesystemInformationWrites
    _,record,extraction=setup(tmp_path);draft=review(record,extraction)
    first=accept_detail(tmp_path,draft,detail=draft['detail'],actor='human');store=backend(tmp_path)
    store.delete_request(first['information_id'],'human','remove',1,'delete-detail')
    writer=FilesystemInformationWrites(store)
    for opid in writer.journal.ids():writer.compact(opid)
    store.approve_delete(first['information_id'],'delete-detail')
    before=hashes(tmp_path)
    assert accept_detail(tmp_path,draft,detail=draft['detail']+' ',actor='other')==first
    assert store.get(first['information_id']) is None and hashes(tmp_path)==before


def seed_v1(root,draft):
    """Publish the historical command exactly as the v1 producer did."""
    import json
    from hashlib import sha256
    from core.backend.models import Memory
    from core.information.writes import FilesystemInformationWrites
    store=backend(root)
    from core.sources.store import SourceStore
    record=SourceStore(root).read(draft['source_id'])[0]
    key=sha256(json.dumps(dict(review=draft,reviewed_detail=draft['detail'],actor='human'),sort_keys=True,ensure_ascii=False).encode()).hexdigest()
    provenance=dict(source_type='MODEL_GENERATED',source=record['source_id'],source_sha256=record['sha256'],
        source_title=record['title'],author=record['author'],extraction_sha256=draft['extraction_sha256'],
        extractor=draft['extractor'],paragraph=draft['paragraph'],quote=draft['quote'],model=draft['model'],
        model_digest=draft['model_digest'],proposed_detail=draft['detail'],validated_by='human',
        review_form_issued_at=draft['proposed_at'],human_accepted=True)
    writer=FilesystemInformationWrites(store)
    result=writer.create(Memory('source-detail-'+key,content=draft['detail'],
        metadata={'type':'INTERPRETATION','epistemic_status':'UNVERIFIED'},provenance=provenance),
        operation_id='source-accept-'+key,event_id='source-event-'+key,actor='human',timestamp=draft['proposed_at'])
    return result,writer,key


@pytest.mark.parametrize('compact',[False,True])
def test_v1_exact_and_variant_replay_preserve_historical_files(tmp_path,compact):
    _,record,extraction=setup(tmp_path);draft=review(record,extraction)
    first,writer,key=seed_v1(tmp_path,draft)
    if compact:writer.compact('source-accept-'+key)
    before=hashes(tmp_path)
    assert accept_detail(tmp_path,draft,detail=draft['detail'],actor='human')==first
    assert accept_detail(tmp_path,dict(draft,model='other'),detail=draft['detail']+' ',actor='other')==first
    assert hashes(tmp_path)==before
    assert 'detail_key_version' not in writer.backend.get(first['information_id']).provenance


def test_deleted_v1_exact_replay_preserved_but_variant_has_documented_limit(tmp_path):
    _,record,extraction=setup(tmp_path);draft=review(record,extraction)
    first,writer,key=seed_v1(tmp_path,draft)
    writer.backend.delete_request(first['information_id'],'human','remove',1,'delete-v1')
    writer.compact('source-accept-'+key)
    writer.backend.approve_delete(first['information_id'],'delete-v1')
    before=hashes(tmp_path)
    assert accept_detail(tmp_path,draft,detail=draft['detail'],actor='human')==first
    assert hashes(tmp_path)==before
    second=accept_detail(tmp_path,draft,detail=draft['detail']+' ',actor='human')
    assert second['information_id'].startswith('source-detail-v2-')
    assert writer.backend.get(first['information_id']) is None


def test_quote_and_paragraph_remain_part_of_identity(tmp_path):
    _,record,extraction=setup(tmp_path);draft=review(record,extraction)
    first=accept_detail(tmp_path,draft,detail=draft['detail'],actor='human')
    second=accept_detail(tmp_path,dict(draft,quote='Lina habite'),detail=draft['detail'],actor='human')
    third=accept_detail(tmp_path,dict(draft,paragraph=2,quote='Elle possède'),detail=draft['detail'],actor='human')
    assert len({v['information_id'] for v in (first,second,third)})==3


def test_concurrent_analyses_publish_one_information(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    _,record,extraction=setup(tmp_path);draft=review(record,extraction)
    def accept(index):
        return accept_detail(tmp_path,dict(draft,model=str(index)),detail=draft['detail'],actor=str(index))
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(accept,range(2)))
    assert results[0]==results[1]
    assert len(backend(tmp_path).list())==1


@pytest.mark.parametrize('compact',[False,True])
def test_historical_v2_vocabulary_replays_without_rewrite(tmp_path,monkeypatch,compact):
    import core.sources.validation as validation
    from core.information.writes import FilesystemInformationWrites
    _,record,extraction=setup(tmp_path);draft=review(record,extraction)
    with monkeypatch.context() as patch:
        patch.setattr(validation,'MODEL_OUTPUT','MODEL_GENERATED')
        first=accept_detail(tmp_path,draft,detail=draft['detail'],actor='human')
    store=backend(tmp_path);writer=FilesystemInformationWrites(store)
    if compact:
        for opid in writer.journal.ids():writer.compact(opid)
    before=hashes(tmp_path)
    assert accept_detail(tmp_path,draft,detail=draft['detail']+' ',actor='other')==first
    assert store.get(first['information_id']).provenance['source_type']=='MODEL_GENERATED'
    assert hashes(tmp_path)==before


def test_model_origin_labels_never_imply_confirmation():
    from core.sources.provenance import is_model_source_type
    for value in ('MODEL_OUTPUT','MODEL_GENERATED','MODEL_INFERENCE'):
        assert is_model_source_type(value)
    for value in ('USER_STATEMENT','SYSTEM_GENERATED','model_output',None,{},[]):
        assert not is_model_source_type(value)
