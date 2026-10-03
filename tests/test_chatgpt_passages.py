import json
from core.backend.filesystem import FilesystemBackend
from core.backend.models import Memory
from core.retrieval.contextual import ContextualRecall


def recall(tmp_path, query, messages, **options):
    backend=FilesystemBackend(tmp_path/'memory/persistent',tmp_path/'memory/history')
    archive=Memory('archive',content=json.dumps({'conversation_id':'c','messages':messages}),
        metadata={'archive_kind':'conversation','epistemic_status':'UNVERIFIED'},
        provenance={'importer':'chatgpt-archive-v1','conversation_id':'c'})
    backend.store(archive)
    return backend, ContextualRecall(backend).recall(query,**options)


def message(text,identity='m',role='user'):
    return dict(content=text,node_id=identity,message_id=identity,parent='p',role=role,created_at=1700000000)


def test_late_match_is_returned_with_exact_source_offsets(tmp_path):
    text='introduction '*500+'Eidolon possède une mémoire durable.'
    backend,bundle=recall(tmp_path,'Eidolon',[message(text)],max_item_chars=80,max_chars=80)
    item=bundle.items[0]
    assert 'Eidolon' in item.content
    ref=item.excerpt_reference
    assert ref['message_id']=='m' and ref['role']=='user' and ref['created_at']==1700000000
    assert text[ref['start']:ref['end']]==item.content
    assert item.needs_review and item.truncated and bundle.used_chars<=80


def test_better_message_selected_without_merging_branches(tmp_path):
    _,bundle=recall(tmp_path,'mémoire robot',[message('robot ancien','a'),message('mémoire du robot','b','assistant')])
    assert bundle.items[0].excerpt_reference['message_id']=='b'
    assert bundle.items[0].excerpt_reference['role']=='assistant'
    assert 'ancien' not in bundle.items[0].content


def test_term_in_json_keys_is_not_a_message_match(tmp_path):
    _,bundle=recall(tmp_path,'messages',[message('autre texte')])
    assert not bundle.items


def test_token_budget_counts_selected_excerpt(tmp_path):
    _,bundle=recall(tmp_path,'Eidolon',[message('x '*500+'Eidolon suite')],
        max_item_chars=100,max_tokens=15,token_counter=len)
    assert bundle.used_tokens<=15
    item=bundle.items[0];assert len(item.content)<=15
    assert item.excerpt_reference['end']-item.excerpt_reference['start']==len(item.content)


def test_later_window_contains_both_terms_under_small_budget(tmp_path):
    text='mémoire '+('ancien '*100)+'mémoire du robot durable'
    _,bundle=recall(tmp_path,'mémoire robot',[message(text)],max_item_chars=40,max_chars=40)
    assert 'mémoire' in bundle.items[0].content and 'robot' in bundle.items[0].content


def test_window_quality_beats_whole_message_term_coverage(tmp_path):
    spread='mémoire '+('ancien '*100)+'robot'
    _,bundle=recall(tmp_path,'mémoire robot',[message(spread,'a'),message('mémoire du robot','b')],
        max_item_chars=40,max_chars=40)
    assert bundle.items[0].excerpt_reference['message_id']=='b'


def test_fully_visible_term_required_by_character_budget(tmp_path):
    _,bundle=recall(tmp_path,'Eidolon',[message('Eidolon')],max_chars=3,max_item_chars=3)
    assert not bundle.items


def test_full_passage_coverage_ranks_above_scattered_terms(tmp_path):
    backend=FilesystemBackend(tmp_path/'memory/persistent',tmp_path/'memory/history')
    for identity,text in [('a-spread','mémoire mémoire mémoire '+('ancien '*200)+'robot robot robot'),
                          ('z-tight','mémoire du robot')]:
        backend.store(Memory(identity,content=json.dumps({'conversation_id':identity,'messages':[message(text)]},ensure_ascii=False),
            metadata={'archive_kind':'conversation','epistemic_status':'UNVERIFIED'},
            provenance={'importer':'chatgpt-archive-v1'}))
    # The first archive has high whole-text frequency, but no useful two-term window at its start.
    result=ContextualRecall(backend).recall('mémoire robot',max_items=1,max_chars=30,max_item_chars=30)
    assert result.items[0].information_id=='z-tight'
    assert result.items[0].ranking['policy']=='lexical_passage_v1'


def test_phrase_match_wins_over_reversed_terms(tmp_path):
    backend=FilesystemBackend(tmp_path/'memory/persistent',tmp_path/'memory/history')
    for identity,text in [('a-reversed','robot mémoire'),('z-phrase','mémoire robot')]:
        backend.store(Memory(identity,content=json.dumps({'conversation_id':identity,'messages':[message(text)]},ensure_ascii=False),
            metadata={'archive_kind':'conversation','epistemic_status':'UNVERIFIED'},
            provenance={'importer':'chatgpt-archive-v1'}))
    result=ContextualRecall(backend).recall('mémoire robot',max_items=1)
    assert result.items[0].information_id=='z-phrase'


def test_metadata_only_archive_is_absent_from_passage_search(tmp_path):
    backend,_=recall(tmp_path,'messages',[message('unrelated')])
    assert not backend.search('messages',{'ranking':'lexical_v1','passage_chars':80})


def test_passage_options_are_explicit_and_validated(tmp_path):
    import pytest
    backend=FilesystemBackend(tmp_path/'memory/persistent',tmp_path/'memory/history')
    for options in ({'ranking':'lexical_v1','passage_chars':0},
                    {'ranking':'lexical_v1','passage_chars':True},
                    {'passage_chars':80}):
        with pytest.raises(ValueError):
            backend.search('',options)
