"""Claude review C1 (10d68a2, 88050bc, b3ae58e, 7805b21): ChatGPT import and recall.

Synthetic exports only, shaped like the ChatGPT export format (mapping/author/
content/recipient/metadata). Red cases are expected defects; others characterize.
"""
import json
import multiprocessing
import os

import pytest

from core.backend.filesystem import FilesystemBackend
from core.operations.readiness import check_readiness
from core.retrieval.contextual import ContextualRecall
from core.sources.chatgpt_import import import_exports, plan_conversation


def node(parent, mid, role, text=None, *, content_type='text', recipient='all', channel=None,
         hidden=False, extra_content=None, t=1700000000):
    content = dict(content_type=content_type)
    if text is not None:
        content['parts'] = [text]
    content.update(extra_content or {})
    message = dict(id=mid, author={'role': role}, create_time=t, content=content, recipient=recipient,
                   metadata={'is_visually_hidden_from_conversation': True} if hidden else {})
    if channel:
        message['channel'] = channel
    return dict(parent=parent, message=message)


def conv(mapping, cid='c-1', t=1700000000, title='t'):
    return dict(id=cid, create_time=t, title=title, current_node=list(mapping)[-1], mapping=mapping)


def imported_texts(conversation):
    memory, _ = plan_conversation(conversation, 'h')
    return [] if memory is None else [m['content'] for m in json.loads(memory.content)['messages']]


# --- message selection -------------------------------------------------------

def test_assistant_tool_call_with_text_content_is_not_imported_as_dialogue():
    """Tool calls (recipient != 'all', e.g. the memory tool 'bio') are technical messages."""
    texts = imported_texts(conv({
        'a': node(None, 'a', 'user', 'question publique'),
        'b': node('a', 'b', 'assistant', 'NOTE-OUTIL interne', recipient='bio'),
        'c': node('b', 'c', 'assistant', 'réponse publique')}))
    assert 'NOTE-OUTIL interne' not in texts


def test_hidden_context_message_is_not_imported_as_dialogue():
    texts = imported_texts(conv({
        'a': node(None, 'a', 'user', 'CONTEXTE-CACHÉ', hidden=True),
        'b': node('a', 'b', 'user', 'question publique')}))
    assert 'CONTEXTE-CACHÉ' not in texts


def test_tool_and_system_roles_and_reasoning_are_excluded():
    texts = imported_texts(conv({
        's': node(None, 's', 'system', 'SYS'),
        'a': node('s', 'a', 'user', 'question'),
        't': node('a', 't', 'tool', 'SORTIE-OUTIL'),
        'r': node('t', 'r', 'assistant', 'RAISONNEMENT', channel='analysis'),
        'th': node('r', 'th', 'assistant', None, content_type='thoughts',
                   extra_content={'thoughts': [{'content': 'PENSEE'}]}),
        'b': node('th', 'b', 'assistant', 'réponse')}))
    assert texts == ['question', 'réponse']


def test_code_messages_are_not_imported_as_dialogue():
    """Export code lives in content.text (tool calls); v1 listed the type but never read it."""
    texts = imported_texts(conv({
        'a': node(None, 'a', 'user', 'question'),
        'b': node('a', 'b', 'assistant', None, content_type='code', recipient='all',
                  extra_content={'language': 'python', 'text': 'print(1)'})}))
    assert texts == ['question']


@pytest.mark.parametrize('broken', [{'author': None}, {'content': None}])
def test_malformed_message_is_refused_as_invalid_input(broken):
    mapping = {'a': node(None, 'a', 'user', 'question')}
    mapping['a']['message'].update(broken)
    with pytest.raises(ValueError):
        plan_conversation(conv(mapping), 'h')


# --- import lifecycle --------------------------------------------------------

def write_export(path, conversations):
    path.write_text(json.dumps(conversations, ensure_ascii=False), encoding='utf-8')
    return path


def count_archives(root):
    return len(list((root / 'memory/persistent').glob('*.md')))


def _import_then_die(root, files, die_after):
    import core.information.writes as writes
    original = writes.FilesystemInformationWrites.create
    calls = []
    def create(self, *a, **k):
        if len(calls) == die_after:
            os._exit(9)
        calls.append(1)
        return original(self, *a, **k)
    writes.FilesystemInformationWrites.create = create
    import_exports(root, files)
    os._exit(0)


@pytest.mark.skipif('fork' not in multiprocessing.get_all_start_methods(), reason='fork required')
def test_import_killed_midway_is_completed_by_replay(tmp_path):
    files = [write_export(tmp_path / '01.json', [
        conv({'a': node(None, 'a', 'user', f'texte {i}')}, cid=f'c-{i}') for i in range(5)])]
    root = tmp_path / 'corpus'
    p = multiprocessing.get_context('fork').Process(target=_import_then_die, args=(root, files, 2))
    p.start(); p.join(60)
    assert p.exitcode == 9 and count_archives(root) == 2
    assert import_exports(root, files)['conversations'] == 5
    assert count_archives(root) == 5 and check_readiness(root)['ready']


def _import(root, files, queue):
    try:
        queue.put(import_exports(root, files)['status'])
    except Exception as exc:  # report, do not hide
        queue.put(f'{type(exc).__name__}: {exc}')


@pytest.mark.skipif('fork' not in multiprocessing.get_all_start_methods(), reason='fork required')
def test_two_concurrent_imports_of_same_files_publish_once(tmp_path):
    files = [write_export(tmp_path / '01.json', [
        conv({'a': node(None, 'a', 'user', f'texte {i}')}, cid=f'c-{i}') for i in range(20)])]
    root = tmp_path / 'corpus'
    ctx = multiprocessing.get_context('fork'); queue = ctx.Queue()
    procs = [ctx.Process(target=_import, args=(root, files, queue)) for _ in range(2)]
    for p in procs: p.start()
    results = [queue.get(timeout=60) for _ in procs]
    for p in procs: p.join(60)
    assert results == ['IMPORTED', 'IMPORTED'], results
    assert count_archives(root) == 20 and check_readiness(root)['ready']


def test_continued_conversation_in_later_export_is_refused_in_one_batch(tmp_path):
    """Characterization: older and newer exports of one conversation cannot be imported together."""
    old = conv({'a': node(None, 'a', 'user', 'début')})
    new = conv({'a': node(None, 'a', 'user', 'début'), 'b': node('a', 'b', 'assistant', 'suite')})
    files = [write_export(tmp_path / '01.json', [old]), write_export(tmp_path / '02.json', [new])]
    with pytest.raises(ValueError, match='conflicting'):
        import_exports(tmp_path / 'corpus', files)


def test_continued_conversation_imported_later_duplicates_recall(tmp_path):
    """Characterization: successive imports keep both versions; recall returns the same message twice."""
    root = tmp_path / 'corpus'
    old = conv({'a': node(None, 'a', 'user', 'Eidolon début')})
    new = conv({'a': node(None, 'a', 'user', 'Eidolon début'), 'b': node('a', 'b', 'assistant', 'suite')})
    import_exports(root, [write_export(tmp_path / '01.json', [old])])
    import_exports(root, [write_export(tmp_path / '02.json', [new])])
    backend = FilesystemBackend(root / 'memory/persistent', root / 'memory/history')
    items = ContextualRecall(backend).recall('Eidolon').items
    refs = [(i.excerpt_reference['conversation_id'], i.excerpt_reference['message_id']) for i in items]
    assert len(items) == 2 and len(set(refs)) == 1


# --- passage selection -------------------------------------------------------

def recall_one(tmp_path, query, text, **options):
    root = tmp_path / 'corpus'
    import_exports(root, [write_export(tmp_path / 'x.json', [conv({'a': node(None, 'a', 'user', text)})])])
    backend = FilesystemBackend(root / 'memory/persistent', root / 'memory/history')
    return ContextualRecall(backend).recall(query, **options).items


def test_passage_offsets_exact_with_emoji_and_combining_accents(tmp_path):
    acute = chr(0x301)  # combining acute accent: decomposed é
    text = (chr(0x1f600) + ' intro e' + acute + 'te' + acute + ' ') * 30 + 'Eidolon garde la mémoire ' + chr(0x1f916) + ' du robot.'
    items = recall_one(tmp_path, 'mémoire robot', text, max_item_chars=60, max_chars=60)
    ref = items[0].excerpt_reference
    assert text[ref['start']:ref['end']] == items[0].content
    assert 'robot' in items[0].content


def test_decomposed_accent_in_archive_matches_composed_query(tmp_path):
    items = recall_one(tmp_path, 'mémoire', 'la me' + chr(0x301) + 'moire du robot')
    assert items and 'moire' in items[0].content


def test_passage_starts_at_first_matched_term_without_left_context(tmp_path):
    """Characterization: the excerpt begins exactly on a query term."""
    items = recall_one(tmp_path, 'robot', 'Hier soir, nous avons parlé du robot de cuisine.')
    assert items[0].content.startswith('robot')


# --- versioning of the importer (proposal v2) ---------------------------------

def seed_v1_corpus(root, conversation):
    """Publish an archive exactly as the v1 importer named it (identity, importer)."""
    from dataclasses import replace
    from core.information.writes import FilesystemInformationWrites
    memory, at = plan_conversation(conversation, 'h')
    digest = memory.provenance['conversation_sha256']
    v1 = replace(memory, information_id='gpt-conversation-v1-' + digest,
                 provenance=dict(memory.provenance, importer='chatgpt-archive-v1'))
    root.mkdir(parents=True, exist_ok=True)
    (root / 'CHATGPT-TEST-CORPUS').write_text('v1\n')
    writer = FilesystemInformationWrites(FilesystemBackend(root / 'memory/persistent', root / 'memory/history'))
    writer.create(v1, operation_id='import-' + v1.information_id, event_id='event-' + v1.information_id,
                  actor='chatgpt-export-importer', timestamp=at)
    return v1


def test_v1_corpus_stays_recallable_with_exact_references(tmp_path):
    root = tmp_path / 'corpus'
    v1 = seed_v1_corpus(root, conv({'a': node(None, 'a', 'user', 'Eidolon garde la mémoire')}))
    backend = FilesystemBackend(root / 'memory/persistent', root / 'memory/history')
    items = ContextualRecall(backend).recall('mémoire').items
    assert [i.information_id for i in items] == [v1.information_id]
    assert items[0].excerpt_reference['message_id'] == 'a'
    assert items[0].ranking['policy'] == 'lexical_passage_v1'


def test_new_import_into_v1_corpus_is_refused_before_any_write(tmp_path):
    from tools.vm_acceptance import hashes
    root = tmp_path / 'corpus'
    c = conv({'a': node(None, 'a', 'user', 'Eidolon garde la mémoire')})
    seed_v1_corpus(root, c)
    before = hashes(root)
    with pytest.raises(ValueError, match='v1'):
        import_exports(root, [write_export(tmp_path / '01.json', [c])])
    assert hashes(root) == before

def test_v1_receipt_after_deletion_still_blocks_mixed_import(tmp_path):
    from core.information.writes import FilesystemInformationWrites
    from tools.vm_acceptance import hashes
    root = tmp_path/'corpus'
    conversation = conv({'a': node(None, 'a', 'user', 'Eidolon memory')})
    v1 = seed_v1_corpus(root, conversation)
    backend = FilesystemBackend(root/'memory/persistent', root/'memory/history')
    backend.delete_request(v1.information_id, 'human', 'remove', 1, 'delete-v1')
    FilesystemInformationWrites(backend).compact('import-'+v1.information_id)
    backend.approve_delete(v1.information_id, 'delete-v1')
    before = hashes(root)
    with pytest.raises(ValueError, match='v1'):
        import_exports(root, [write_export(tmp_path/'export.json', [conversation])])
    assert hashes(root) == before


def test_cli_invalid_message_returns_blocked_without_publication(tmp_path, capsys):
    from core.sources.chatgpt_import import main
    conversation = conv({'a': node(None, 'a', 'user', 'question')})
    conversation['mapping']['a']['message']['author'] = None
    file = write_export(tmp_path/'export.json', [conversation])
    assert main(['--root', str(tmp_path/'corpus'), str(file)]) == 1
    output = capsys.readouterr()
    assert json.loads(output.out)['status'] == 'BLOCKED'
    assert not output.err and not (tmp_path/'corpus').exists()


def test_pending_v1_journal_without_information_blocks_v2(tmp_path, monkeypatch):
    from tools.vm_acceptance import hashes
    root = tmp_path/'corpus'
    conversation = conv({'a': node(None, 'a', 'user', 'Eidolon memory')})
    def stop(*args, **kwargs):
        raise RuntimeError('before Information')
    with monkeypatch.context() as patch:
        patch.setattr(FilesystemBackend, '_atomic_write', stop)
        with pytest.raises(RuntimeError, match='before Information'):
            seed_v1_corpus(root, conversation)
    assert not list((root/'memory/persistent').glob('*.md'))
    assert not check_readiness(root)['ready']
    before = hashes(root)
    with pytest.raises(ValueError, match='v1'):
        import_exports(root, [write_export(tmp_path/'export.json', [conversation])])
    assert hashes(root) == before


def test_import_version_is_rechecked_under_persistent_lock(tmp_path, monkeypatch):
    import core.sources.chatgpt_import as module
    from core.persistence import write_lock_held
    from tools.vm_acceptance import hashes
    root = tmp_path/'corpus'
    conversation = conv({'a': node(None, 'a', 'user', 'Eidolon memory')})
    seed_v1_corpus(root, conversation)
    before = hashes(root)
    original = module._check_import_version
    calls = []
    def simulate_initial_inspection_missing_v1(path):
        calls.append(write_lock_held(path/'memory/persistent'))
        if len(calls) > 1:
            original(path)
    monkeypatch.setattr(module, '_check_import_version', simulate_initial_inspection_missing_v1)
    with pytest.raises(ValueError, match='v1'):
        import_exports(root, [write_export(tmp_path/'export.json', [conversation])])
    assert calls == [False, True]
    assert hashes(root) == before
