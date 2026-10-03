"""Client budgets include JSON metadata and explicit prompt framing."""
from dataclasses import asdict,replace
import json
import pytest

from core.retrieval.context import ContextItem
from core.retrieval.contextual import RecallBundle,RecallItem
from core.retrieval.payload import render


def item(identity,content='claim',**changes):
    values=dict(information_id=identity,revision=1,content=content,score=1.0,
        ranking={'profile':'lexical_v1'},truncated=False,epistemic_status='UNVERIFIED',
        operational_state=None,confidence=None,needs_review=True,
        provenance={'source':'human'},context={'scope':{'goal':'efficiency'}})
    values.update(changes)
    return RecallItem(**values)


def bundle(*items):
    return RecallBundle('claim','operational',{'goal':'efficiency'},None,tuple(items),
                        sum(len(item.content) for item in items),None,{'EXPIRED':1})


def serialized(value):
    return json.dumps(asdict(value),ensure_ascii=False,sort_keys=True,separators=(',',':'))


def test_exact_payload_preserves_every_metadata_field_and_unicode():
    original=bundle(item('one','mémorisé',temporal={'valid_until':'2026-11-01T00:00:00Z'},
        verification={'evidence':'human-reviewed'},relations=({'target':'other'},)))
    result=render(original,max_payload_chars=10000)
    assert result.text==serialized(original)
    assert result.payload_chars==len(result.text) and result.payload_tokens is None
    assert result.included_ids==('one',) and result.omitted_ids==()
    assert json.loads(result.text)['items'][0]['needs_review'] is True


def test_budget_drops_whole_oversized_item_and_keeps_later_small_item():
    large=item('huge',provenance={'source':'X'*5000});small=item('small')
    original=bundle(large,small)
    expected=replace(original,items=(small,),used_chars=len(small.content),
                     excluded_counts={'EXPIRED':1,'PAYLOAD_BUDGET':1})
    limit=len(serialized(expected))
    result=render(original,max_payload_chars=limit)
    assert result.text==serialized(expected) and result.payload_chars==limit
    assert result.included_ids==('small',) and result.omitted_ids==('huge',)
    assert original.items==(large,small) and original.excluded_counts=={'EXPIRED':1}


def test_empty_payload_is_explicit_when_no_full_source_fits():
    original=bundle(item('huge',verification={'evidence':'Y'*5000}))
    expected=replace(original,items=(),used_chars=0,excluded_counts={'EXPIRED':1,'PAYLOAD_BUDGET':1})
    result=render(original,max_payload_chars=len(serialized(expected)))
    assert result.text==serialized(expected) and result.omitted_ids==('huge',)


def test_no_budget_can_strip_review_provenance_or_relations_to_fit():
    source=item('huge',relations=({'target':'A'*4000},))
    result=render(bundle(source),max_payload_chars=700)
    assert json.loads(result.text)['items']==[] and result.omitted_ids==('huge',)


def test_header_larger_than_budget_is_rejected_instead_of_truncated():
    with pytest.raises(ValueError):render(bundle(),max_payload_chars=1)


def test_explicit_prompt_framing_is_inside_character_budget():
    original=bundle(item('one'));prefix='Instruction : ';suffix='\nRéponds avec prudence.'
    expected=prefix+serialized(original)+suffix
    result=render(original,max_payload_chars=len(expected),prefix=prefix,suffix=suffix)
    assert result.text==expected and result.payload_chars==len(expected)
    with pytest.raises(ValueError):render(bundle(),max_payload_chars=20,prefix='X'*30)


def test_payload_counter_counts_full_render_and_is_not_sum_of_item_tokens():
    original=bundle(item('one'),item('two'))
    prefix='START';suffix='END'
    calls=[]
    def counter(text):
        calls.append(text)
        return len(text)//3 + (100 if '"idontmatch"' in text else 0)
    full=prefix+serialized(original)+suffix
    result=render(original,max_payload_chars=10000,max_payload_tokens=counter(full),
                  payload_token_counter=counter,prefix=prefix,suffix=suffix)
    assert result.text==full and result.payload_tokens==counter(result.text)
    assert all(text.startswith(prefix) and text.endswith(suffix) for text in calls)


def test_token_budget_can_drop_item_even_when_characters_fit():
    original=bundle(item('one','X'*800),item('two'))
    def counter(text):return len(text)
    expected=replace(original,items=(original.items[1],),used_chars=5,
                     excluded_counts={'EXPIRED':1,'PAYLOAD_BUDGET':1})
    result=render(original,max_payload_chars=10000,max_payload_tokens=len(serialized(expected)),payload_token_counter=counter)
    assert result.text==serialized(expected) and result.omitted_ids==('one',)


@pytest.mark.parametrize('value',[0,-1,True,'100',None])
def test_invalid_character_budget_is_rejected(value):
    with pytest.raises(ValueError):render(bundle(),max_payload_chars=value)


@pytest.mark.parametrize('value',[0,-1,True,'100'])
def test_invalid_token_budget_is_rejected(value):
    with pytest.raises(ValueError):render(bundle(),max_payload_chars=1000,max_payload_tokens=value,payload_token_counter=len)


def test_token_limit_requires_explicit_counter():
    with pytest.raises(ValueError):render(bundle(),max_payload_chars=1000,max_payload_tokens=100)


@pytest.mark.parametrize('value',[-1,True,1.5,'1'])
def test_invalid_counter_result_is_rejected(value):
    with pytest.raises(ValueError):render(bundle(),max_payload_chars=1000,max_payload_tokens=100,payload_token_counter=lambda text:value)


def test_excerpt_tokens_are_recomputed_after_omission():
    original=replace(bundle(item('huge','X'*2000,token_count=2000),item('small',token_count=5)),used_tokens=2005)
    expected=replace(original,items=(original.items[1],),used_chars=5,used_tokens=5,
                     excluded_counts={'EXPIRED':1,'PAYLOAD_BUDGET':1})
    result=render(original,max_payload_chars=len(serialized(expected)))
    assert result.text==serialized(expected)


def test_counted_excerpt_bundle_requires_valid_item_counts():
    original=replace(bundle(item('one')),used_tokens=5)
    with pytest.raises(ValueError):render(original,max_payload_chars=10000)


def test_nonadditive_token_counter_is_applied_to_each_full_candidate():
    original=bundle(item('one','X'*800),item('two'))
    seen=[]
    def counter(text):
        seen.append(text)
        return 1000 if 'X'*800 in text else 1
    result=render(original,max_payload_chars=10000,max_payload_tokens=1,payload_token_counter=counter)
    assert result.included_ids==('two',) and result.payload_tokens==1
    assert all(json.loads(text)['query']=='claim' for text in seen)


@pytest.mark.parametrize('prefix,suffix',[(None,''),('',None),(1,''),('',{})])
def test_invalid_framing_is_rejected(prefix,suffix):
    with pytest.raises(ValueError):render(bundle(),max_payload_chars=1000,prefix=prefix,suffix=suffix)


def test_facade_reads_canonical_uncertain_source_without_mutation(tmp_path):
    from core.routing.execution import RoutingExecutor
    from tests.test_contextual_recall import backend,store
    from tests.test_migration_converter import fingerprints
    data=backend(tmp_path);source=store(data,'one',status='UNVERIFIED')
    executor=RoutingExecutor(data)
    before=fingerprints(tmp_path)
    result=executor.recall_payload('power',query_scope={'goal':'efficiency'},max_payload_chars=10000)
    value=json.loads(result.text)
    assert value['items'][0]['information_id']=='one' and value['items'][0]['needs_review'] is True
    assert value['items'][0]['provenance']==source.provenance and result.payload_chars==len(result.text)
    # Reader locking can create technical lock files, never business artifacts.
    after=fingerprints(tmp_path)
    assert {k:v for k,v in before.items() if not k.endswith('.write.lock')}=={k:v for k,v in after.items() if not k.endswith('.write.lock')}


def test_historical_payload_keeps_pending_delete_warning_and_source_metadata(tmp_path):
    from core.routing.execution import RoutingExecutor
    from tests.test_contextual_recall import backend,store
    data=backend(tmp_path);store(data,'one',status='UNVERIFIED')
    data.delete_request('one','human','Review',1,'delete')
    result=RoutingExecutor(data).recall_payload('power',query_scope={'goal':'efficiency'},mode='historical',max_payload_chars=10000)
    value=json.loads(result.text)['items'][0]
    assert value['needs_review'] and 'pending_deletion' in value['selection_reasons']
    assert value['epistemic_status']=='UNVERIFIED' and data.get('one').revision==1


def test_payload_keeps_global_readiness_guard(tmp_path):
    from core.operations.errors import OperationConflict
    from core.routing.execution import RoutingExecutor
    from tests.test_contextual_recall import backend,store
    data=backend(tmp_path);store(data,'one')
    path=data.history_root/'operations/unknown/one.json';path.parent.mkdir(parents=True);path.write_text('{}')
    with pytest.raises(OperationConflict):RoutingExecutor(data).recall_payload('power',max_payload_chars=10000)


def test_invalid_payload_budget_fails_before_reading_engine(monkeypatch):
    from core.retrieval.contextual import ContextualRecall
    reader=ContextualRecall.__new__(ContextualRecall)
    monkeypatch.setattr(reader,'recall',lambda *args,**kwargs:pytest.fail('engine was read'))
    with pytest.raises(ValueError):reader.recall_payload('power',max_payload_chars=0)


def test_facade_distinguishes_excerpt_tokens_from_whole_payload_tokens(tmp_path):
    from core.routing.execution import RoutingExecutor
    from tests.test_contextual_recall import backend,store
    data=backend(tmp_path);store(data,'one')
    result=RoutingExecutor(data).recall_payload('power',max_payload_chars=10000,max_payload_tokens=10000,
        payload_token_counter=len,max_tokens=3,token_counter=len)
    value=json.loads(result.text)
    assert value['used_tokens']==3 and value['items'][0]['content']=='pow'
    assert result.payload_tokens==len(result.text)>3


def test_cli_emits_exact_budgeted_json_without_extra_whitespace(tmp_path,capsys):
    from core.routing.execution_cli import main
    from core.routing.execution import RoutingExecutor
    from tests.test_contextual_recall import backend,store
    data=backend(tmp_path);store(data,'one',status='UNVERIFIED')
    scope=tmp_path/'scope.json';scope.write_text(json.dumps({'goal':'efficiency'}))
    expected=RoutingExecutor(data).recall_payload('power',query_scope={'goal':'efficiency'},max_payload_chars=10000)
    assert main(['--root',str(tmp_path),'recall-payload','power','--scope',str(scope),'--max-payload-chars',str(expected.payload_chars)])==0
    text=capsys.readouterr().out
    assert text==expected.text and len(text)==expected.payload_chars


def test_cli_counts_supplied_client_framing(tmp_path,capsys):
    from core.routing.execution_cli import main
    from tests.test_contextual_recall import backend,store
    data=backend(tmp_path);store(data,'one')
    scope=tmp_path/'scope.json';scope.write_text('{}')
    assert main(['--root',str(tmp_path),'recall-payload','power','--scope',str(scope),'--max-payload-chars','10000','--prefix','START\n','--suffix','\nEND'])==0
    text=capsys.readouterr().out
    assert text.startswith('START\n') and text.endswith('\nEND') and json.loads(text[6:-4])['items'][0]['information_id']=='one'
