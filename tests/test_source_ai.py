from dataclasses import replace
import json

import pytest

from core.sources.local_ai import LocalDetailAI
from core.sources.validation import accept_detail, seal, unseal
from tests.test_source_library import seed, add, STAMP
from core.backend.filesystem import FilesystemBackend
from tools.vm_acceptance import hashes


def setup(root):
    store = seed(root)
    record = add(store, 'Lina habite à Lyon.\nElle possède un chat nommé Plume.'.encode(), original_name='story.txt')['source']
    extraction = store.extract(record['source_id'])['extraction']
    return store, record, extraction


def fake_ai(monkeypatch, details=None):
    ai = LocalDetailAI(model='qwen3:0.6b')
    calls = []
    def request(path, payload=None):
        calls.append((path, payload))
        if path == '/api/tags':
            return {'models': [{'name': ai.model, 'digest': 'a'*64}]}
        return {'model': ai.model, 'done': True, 'response': json.dumps({'details': details if details is not None else [
            {'detail': 'Dans cette source, Lina habite à Lyon.', 'paragraph': 1, 'quote': 'Lina habite à Lyon.'}]})}
    monkeypatch.setattr(ai, '_request', request)
    return ai, calls


def test_local_ai_bounded_drafts_have_exact_support_without_writes(tmp_path, monkeypatch):
    store, record, extraction = setup(tmp_path)
    ai, calls = fake_ai(monkeypatch)
    before = hashes(tmp_path)
    draft = ai.propose(record, extraction)
    assert hashes(tmp_path) == before and draft['details'][0]['paragraph'] == 1
    assert draft['model_digest'] == 'a'*64
    payload = calls[1][1]
    assert payload['keep_alive'] == 0 and payload['stream'] is False and payload['think'] is False
    assert payload['options']['num_thread'] == 1 and payload['options']['num_ctx'] == 4096
    assert draft['next_paragraph'] is None


def test_exact_quote_repairs_wrong_paragraph_without_writes(tmp_path, monkeypatch):
    _, record, extraction = setup(tmp_path)
    ai, _ = fake_ai(monkeypatch, [dict(detail='Le chat se nomme Plume.',
        paragraph=1, quote='Elle possède un chat nommé Plume.')])
    before = hashes(tmp_path)
    result = ai.propose(record, extraction)
    assert result['details'][0]['paragraph'] == 2
    assert hashes(tmp_path) == before


def test_wrong_paragraph_with_ambiguous_quote_is_rejected(tmp_path, monkeypatch):
    _, record, extraction = setup(tmp_path)
    extraction = dict(extraction, paragraphs=['Autre passage.', 'Citation répétée.', 'Citation répétée.'])
    ai, _ = fake_ai(monkeypatch, [dict(detail='Un détail.', paragraph=1, quote='Citation répétée.')])
    with pytest.raises(ValueError, match='unique exact source support'):
        ai.propose(record, extraction)


@pytest.mark.parametrize('item', [
    {'detail':'Invented', 'paragraph':1, 'quote':'not in the source'},
    {'detail':'Invented', 'paragraph':99, 'quote':'Lina'},
    {'detail':'', 'paragraph':1, 'quote':'Lina'},
    {'detail':'x', 'paragraph':True, 'quote':'Lina'},
    {'detail':'x', 'paragraph':1, 'quote':''},
])
def test_invalid_model_reference_creates_no_memories(tmp_path, monkeypatch, item):
    _, record, extraction = setup(tmp_path)
    ai, _ = fake_ai(monkeypatch, [item])
    before = hashes(tmp_path)
    with pytest.raises(ValueError):
        ai.propose(record, extraction)
    assert hashes(tmp_path) == before


@pytest.mark.parametrize('url,model', [
    ('https://example.com','qwen3:0.6b'), ('http://192.168.1.10:11434','qwen3:0.6b'),
    ('http://127.0.0.1:11435','model-cloud'), ('http://user@127.0.0.1:11435','qwen3:0.6b'),
])
def test_remote_or_cloud_inference_is_not_accepted(url, model):
    with pytest.raises(ValueError):
        LocalDetailAI(model=model, endpoint=url)


def review(record, extraction):
    return dict(source_id=record['source_id'], source_sha256=record['sha256'],
        extraction_sha256=extraction['text_sha256'], extractor=extraction['extractor'],
        model='qwen3:0.6b', model_digest='a'*64, proposed_at=STAMP,
        paragraph=1, detail='Lina vit à Lyon.', quote='Lina habite à Lyon.')


def test_acceptance_creates_only_reviewed_detail_with_provenance_and_idempotent_replay(tmp_path):
    store, record, extraction = setup(tmp_path)
    draft = review(record, extraction)
    token = seal(draft, b'secret')
    verified = unseal(token, b'secret')
    accepted = accept_detail(tmp_path, verified, detail='Dans le récit, Lina habite à Lyon.', actor='human')
    backend = FilesystemBackend(tmp_path / 'memory/persistent', tmp_path / 'memory/history')
    memory = backend.get(accepted['information_id'])
    assert memory.content == 'Dans le récit, Lina habite à Lyon.'
    assert memory.metadata['epistemic_status'] == 'UNVERIFIED'
    assert memory.provenance['source_type'] == 'MODEL_GENERATED'
    assert memory.provenance['human_accepted'] is True
    assert memory.provenance['source_sha256'] == record['sha256']
    assert memory.provenance['paragraph'] == 1 and memory.provenance['quote'] == draft['quote']
    before = hashes(tmp_path)
    assert accept_detail(tmp_path, verified, detail=memory.content, actor='human') == accepted
    assert hashes(tmp_path) == before
    assert len(list(backend.persistent_root.glob('*.md'))) == 1


def test_changed_review_signature_and_stale_snapshot_are_refused(tmp_path):
    store, record, extraction = setup(tmp_path)
    draft = review(record, extraction)
    token = seal(draft, b'secret')
    with pytest.raises(ValueError):
        unseal(token, b'other-secret')
    before = hashes(tmp_path)
    draft['extraction_sha256'] = 'b'*64
    with pytest.raises(ValueError):
        accept_detail(tmp_path, draft, detail='Changed', actor='human')
    assert hashes(tmp_path) == before


def test_reference_replay_does_not_resurrect_deleted_memory_or_delete_source(tmp_path):
    store, record, extraction = setup(tmp_path)
    draft = review(record, extraction)
    result = accept_detail(tmp_path, draft, detail=draft['detail'], actor='human')
    backend = FilesystemBackend(tmp_path / 'memory/persistent', tmp_path / 'memory/history')
    identity = result['information_id']
    backend.delete_request(identity, 'human', 'remove', 1, 'delete-detail')
    from core.information.writes import FilesystemInformationWrites
    writer = FilesystemInformationWrites(backend)
    for operation_id in writer.journal.ids():
        writer.compact(operation_id)
    backend.approve_delete(identity, 'delete-detail')
    assert accept_detail(tmp_path, draft, detail=draft['detail'], actor='human') == result
    assert backend.get(identity) is None
    assert store.read(record['source_id'])[0] == record


def test_model_response_quote_is_rechecked_on_acceptance(tmp_path):
    store, record, extraction = setup(tmp_path)
    draft = review(record, extraction)
    draft['quote'] = 'Not in source'
    before = hashes(tmp_path)
    with pytest.raises(ValueError):
        accept_detail(tmp_path, draft, detail='Unsupported', actor='human')
    assert hashes(tmp_path) == before


def test_proposal_pass_reports_exact_remaining_coverage(tmp_path, monkeypatch):
    store, record, extraction = setup(tmp_path)
    more = dict(extraction, paragraphs=['line '+str(i) for i in range(25)])
    ai, calls = fake_ai(monkeypatch, details=[])
    result = ai.propose(record, more, start=1)
    assert result['first_paragraph'] == 1 and result['last_paragraph'] == 20
    assert result['next_paragraph'] == 21
    assert len(json.loads(calls[1][1]['prompt'])) == 20


def test_inference_error_releases_analysis_slot(tmp_path, monkeypatch):
    _, record, extraction = setup(tmp_path)
    ai, calls = fake_ai(monkeypatch)
    original = ai._request
    def unavailable(path, payload=None):
        raise ValueError('unavailable')
    monkeypatch.setattr(ai,'_request',unavailable)
    with pytest.raises(ValueError):
        ai.propose(record,extraction)
    monkeypatch.setattr(ai,'_request',original)
    assert ai.propose(record,extraction)['details']


def test_blank_paragraphs_do_not_consume_analysis_slots_or_renumber_quotes(tmp_path, monkeypatch):
    _, record, extraction = setup(tmp_path)
    paragraphs = [''] * 25 + ['Lina habite à Lyon.'] + ['   '] * 10 + ['Texte '+str(i) for i in range(25)]
    extraction = dict(extraction, paragraphs=paragraphs)
    ai, calls = fake_ai(monkeypatch, [dict(detail='Lina habite à Lyon.', paragraph=26, quote='Lina habite à Lyon.')])
    result = ai.propose(record, extraction)
    sent = json.loads(calls[1][1]['prompt'])
    assert len(sent) == 20 and sent[0]['paragraph'] == 26
    assert all(item['text'].strip() for item in sent)
    assert result['details'][0]['paragraph'] == 26
    assert result['last_paragraph'] == 55 and result['next_paragraph'] == 56


def test_blank_only_tail_completes_without_loading_model(tmp_path, monkeypatch):
    _, record, extraction = setup(tmp_path)
    extraction = dict(extraction, paragraphs=['Lina.', '', '   '])
    ai, calls = fake_ai(monkeypatch, [])
    result = ai.propose(record, extraction, start=2)
    assert result['details'] == [] and result['next_paragraph'] is None
    assert result['first_paragraph'] == 2 and result['last_paragraph'] == 3
    assert not calls
