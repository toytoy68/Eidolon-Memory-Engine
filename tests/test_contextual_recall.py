"""Context/time/epistemic policy is applied before excerpt budgets."""
from dataclasses import replace

import pytest

from core.backend.filesystem import FilesystemBackend
from core.backend.models import Memory
from core.information.writes import FilesystemInformationWrites
from core.operations.errors import OperationConflict
from core.retrieval.contextual import ContextualRecall
from tests.test_routing_execution import seed, preview, execute, STAMP


def store(backend, identity, *, scope=None, until=None, status='CONFIRMED', content='power measurement'):
    memory = Memory(identity, content=content, metadata={'epistemic_status':status,
                    'context': {'scope': scope if scope is not None else {'goal':'efficiency'}}},
                    provenance={'source':'bench','actor':'human'},
                    verification={'evidence':{'supporting':['measurement']}},
                    temporal={} if until is None else {'valid_until':until})
    backend.store(memory)
    return memory


def backend(root):
    return FilesystemBackend(root / 'memory/persistent', root / 'memory/history')


def test_operational_filters_expired_wrong_context_and_refuted_before_budget(tmp_path):
    data = backend(tmp_path)
    store(data,'a-expired',until='2026-01-01T00:00:00Z')
    store(data,'b-wrong',scope={'goal':'speed'})
    store(data,'c-refuted',status='REFUTED')
    store(data,'d-replaced',status='SUPERSEDED')
    wanted = store(data,'z-current')
    result = ContextualRecall(data).recall('power measurement', query_scope={'goal':'efficiency'}, at=STAMP,
                                         max_items=1, max_chars=7, max_item_chars=7)
    assert [item.information_id for item in result.items] == ['z-current']
    item=result.items[0]
    assert item.content == 'power m' and item.truncated and result.used_chars == 7
    assert item.applicability == 'MATCH' and not item.needs_review
    assert item.provenance == wanted.provenance and item.verification == wanted.verification
    assert result.excluded_counts == {'EXPIRED':1,'OUT_OF_SCOPE':1,'REFUTED':1,'SUPERSEDED':1}


def test_historical_mode_labels_expired_and_refuted_without_rewriting_them(tmp_path):
    data = backend(tmp_path)
    original = store(data,'old',until='2026-01-01T00:00:00Z',status='REFUTED')
    item = ContextualRecall(data).recall('power',query_scope={'goal':'efficiency'},at=STAMP,mode='historical').items[0]
    assert item.applicability == 'EXPIRED' and item.epistemic_status == 'REFUTED'
    assert item.needs_review and 'historical_mode' in item.selection_reasons
    assert data.get('old') == original


@pytest.mark.parametrize('scope,status,expected', [({},'CONFIRMED','UNKNOWN'),
                            ({'goal':'efficiency'},'CONFLICTED','UNRESOLVED'),
                            ({'goal':'efficiency'},'UNVERIFIED','MATCH')])
def test_unknown_conflict_and_unverified_are_visible_but_require_review(tmp_path,scope,status,expected):
    data=backend(tmp_path); store(data,'item',scope=scope,status=status)
    item=ContextualRecall(data).recall('power',query_scope={'goal':'efficiency'},at=STAMP).items[0]
    assert item.applicability == expected and item.needs_review
    assert item.epistemic_status == status


def test_filters_continue_beyond_first_page(tmp_path):
    data=backend(tmp_path)
    for i in range(101):
        store(data,f'a-{i:03}',until='2026-01-01T00:00:00Z')
    store(data,'z-current')
    result=ContextualRecall(data).recall('power',query_scope={'goal':'efficiency'},at=STAMP,max_items=1)
    assert result.items[0].information_id == 'z-current'
    assert result.excluded_counts == {'EXPIRED':101}


def test_full_project_journey_then_correction_reads_canonical_and_flags_stale_view(tmp_path):
    data,executor,memory=seed(tmp_path)
    execute(executor,preview(executor,memory))
    result=executor.recall('measure',query_scope={'goal':'efficiency'},at=STAMP,project_id='project')
    assert result.items[0].content == memory.content and result.dossier_status == 'CURRENT'
    writes=FilesystemInformationWrites(data)
    writes.update(replace(memory,content='measure corrected'),previous_revision=1,operation_id='outside-route',
                  event_id='outside-event',actor='human',timestamp=STAMP)
    result=executor.recall('measure',query_scope={'goal':'efficiency'},at=STAMP,project_id='project')
    assert result.items[0].content == 'measure corrected' and result.items[0].revision == 2
    assert result.dossier_status == 'STALE'
    assert result.items[0].freshness == 'CANONICAL_AT_READ'


def test_incomplete_journey_blocks_recall_instead_of_returning_partial_context(tmp_path,monkeypatch):
    data,executor,memory=seed(tmp_path)
    prepared=preview(executor,memory)
    def stop(stage):
        if stage=='after_information': raise RuntimeError('stop')
    monkeypatch.setattr(executor,'_checkpoint',stop)
    with pytest.raises(RuntimeError): execute(executor,prepared)
    with pytest.raises(OperationConflict,match='readiness'):
        executor.recall('measure',query_scope={'goal':'efficiency'},at=STAMP)


def test_pending_delete_is_explained_and_only_included_in_history(tmp_path):
    data=backend(tmp_path);store(data,'item')
    data.delete_request('item','human','test',1,'delete')
    reader=ContextualRecall(data)
    current=reader.recall('power',query_scope={'goal':'efficiency'},at=STAMP)
    assert not current.items and current.excluded_counts=={'PENDING_DELETE':1}
    old=reader.recall('power',query_scope={'goal':'efficiency'},at=STAMP,mode='historical').items[0]
    assert old.needs_review and 'pending_deletion' in old.selection_reasons


def test_tokens_apply_after_filter_and_source_metadata_is_not_aliased(tmp_path):
    data=backend(tmp_path);store(data,'a',until='2026-01-01T00:00:00Z');store(data,'b')
    result=ContextualRecall(data).recall('power',query_scope={'goal':'efficiency'},at=STAMP,
                                      max_tokens=5,token_counter=len)
    assert result.used_tokens==5 and result.items[0].content=='power'
    result.items[0].provenance['source']='edited'
    assert data.get('b').provenance['source']=='bench'


@pytest.mark.parametrize('kwargs',[{'mode':'automatic'},{'at':'2026-10-01'},{'query_scope':[]}])
def test_invalid_recall_policy_is_rejected(tmp_path,kwargs):
    with pytest.raises(ValueError):
        ContextualRecall(backend(tmp_path)).recall('power',**kwargs)


def test_cli_recall_after_full_journey(tmp_path,capsys):
    import json
    from core.routing.execution_cli import main
    data,executor,memory=seed(tmp_path)
    execute(executor,preview(executor,memory))
    scope=tmp_path/'scope.json';scope.write_text(json.dumps({'goal':'efficiency'}))
    assert main(['--root',str(tmp_path),'recall','measure','--scope',str(scope),
                 '--at',STAMP,'--project-id','project'])==0
    result=json.loads(capsys.readouterr().out)
    assert result['items'][0]['information_id']=='second'
    assert result['items'][0]['provenance']==memory.provenance
    assert result['items'][0]['needs_review'] is True  # UNVERIFIED is never promoted.
    assert result['dossier_status']=='CURRENT'


def test_stale_search_hit_is_not_returned(tmp_path,monkeypatch):
    from core.backend.models import SearchResult
    data=backend(tmp_path);old=store(data,'item')
    data.update('item',replace(old,content='changed'),previous_revision=1)
    monkeypatch.setattr(data,'search',lambda *args:[SearchResult(old,score=1.0)])
    result=ContextualRecall(data).recall('power',query_scope={'goal':'efficiency'},at=STAMP)
    assert not result.items and result.excluded_counts=={'STALE_CANDIDATE':1}
