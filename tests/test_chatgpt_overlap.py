# ==========================================================
# Projet      : Eidolon Memory Engine
# Organisation: Eidolon Core Technologies (ECT)
# Fichier     : tests/test_chatgpt_overlap.py
# Description : Imports recouvrants, reprise et suppression sans résurrection
# Standard    : Eidolon Presentation Standard v1
# ==========================================================

"""Synthetic exports; imported commands remain exactly replayable."""
import json
from hashlib import sha256

import pytest

from core.backend.filesystem import FilesystemBackend
from core.information.writes import FilesystemInformationWrites
from core.operations.readiness import check_readiness
from core.sources.chatgpt_import import import_exports, plan_conversation


def conversation(cid):
    return dict(id=cid, create_time=1700000000, mapping={
        'a': dict(parent=None, message=dict(id='a', author={'role': 'user'},
            content={'content_type': 'text', 'parts': [f'archive {cid}']}))})


def export(path, values, **options):
    path.write_text(json.dumps(values, **options), encoding='utf-8')
    return path


def files(root):
    return {str(p.relative_to(root)): p.read_bytes() for p in root.rglob('*')
            if p.is_file() and p.name != '.write.lock'}


@pytest.mark.parametrize('reverse', [False, True])
def test_overlapping_exports_preserve_first_command_and_all_originals(tmp_path, reverse):
    root = tmp_path / 'corpus'
    a = export(tmp_path / 'a.json', [conversation('c1')])
    b = export(tmp_path / 'b.json', [conversation('c2'), conversation('c1')], indent=2)
    first, second = (b, a) if reverse else (a, b)
    import_exports(root, [first])
    before = files(root / 'memory')
    result = import_exports(root, [second])
    assert result['status'] == 'IMPORTED'
    assert result['replayed_conversations'] == 1
    assert result['new_conversations'] == (0 if reverse else 1)
    for path, raw in before.items():
        assert files(root / 'memory')[path] == raw
    assert len(list((root / 'memory/persistent').glob('*.md'))) == 2
    for source in (a, b):
        assert (root / 'import-originals' / (sha256(source.read_bytes()).hexdigest() + '.json')).read_bytes() == source.read_bytes()
    assert check_readiness(root)['ready']
    unchanged = files(root)
    import_exports(root, [second])
    assert files(root) == unchanged


def test_serialization_change_replays_compacted_deleted_archive(tmp_path):
    root = tmp_path / 'corpus'
    item = conversation('c1')
    a = export(tmp_path / 'a.json', [item])
    b = export(tmp_path / 'b.json', [item], indent=4, sort_keys=True)
    import_exports(root, [a])
    identity = plan_conversation(item, sha256(a.read_bytes()).hexdigest())[0].information_id
    backend = FilesystemBackend(root / 'memory/persistent', root / 'memory/history')
    writer = FilesystemInformationWrites(backend)
    writer.compact('import-' + identity)
    backend.delete_request(identity, 'human', 'obsolete', 1, 'delete-archive')
    backend.approve_delete(identity, 'delete-archive')
    before = files(root / 'memory')
    assert import_exports(root, [b])['replayed_conversations'] == 1
    assert backend.get(identity) is None
    assert files(root / 'memory') == before
    assert check_readiness(root)['ready']


def test_pending_command_replays_original_export_after_interruption(tmp_path, monkeypatch):
    root = tmp_path / 'corpus'
    a = export(tmp_path / 'a.json', [conversation('c1')])
    b = export(tmp_path / 'b.json', [conversation('c1')], indent=2)
    real = FilesystemInformationWrites._resume
    def stop(*args, **kwargs):
        raise OSError('synthetic interruption')
    monkeypatch.setattr(FilesystemInformationWrites, '_resume', stop)
    with pytest.raises(ValueError):
        import_exports(root, [a])
    monkeypatch.setattr(FilesystemInformationWrites, '_resume', real)
    result = import_exports(root, [b])
    assert result['replayed_conversations'] == 1
    assert check_readiness(root)['ready']


def test_known_conflict_is_detected_before_new_original_or_archive(tmp_path):
    root = tmp_path / 'corpus'
    c1 = conversation('c1')
    a = export(tmp_path / 'a.json', [c1])
    b = export(tmp_path / 'b.json', [conversation('c2'), c1])
    import_exports(root, [a])
    # Remove the source needed to prove the exact original command.
    next((root / 'import-originals').glob('*.json')).unlink()
    before = files(root)
    with pytest.raises(ValueError, match='original command'):
        import_exports(root, [b])
    assert files(root) == before


def _die_after_prepare(root, source):
    import os
    FilesystemInformationWrites._resume = lambda *args, **kwargs: os._exit(87)
    import_exports(root, [source])


def test_real_process_death_replays_original_command(tmp_path):
    import multiprocessing
    if 'fork' not in multiprocessing.get_all_start_methods():
        pytest.skip('requires fork')
    root = tmp_path / 'corpus'
    a = export(tmp_path / 'a.json', [conversation('c1')])
    b = export(tmp_path / 'b.json', [conversation('c1')], indent=2)
    child = multiprocessing.get_context('fork').Process(target=_die_after_prepare, args=(root, a))
    child.start()
    try:
        child.join(10)
        assert not child.is_alive()
        assert child.exitcode == 87
    finally:
        if child.is_alive():
            child.terminate()
            child.join(10)
    assert not check_readiness(root)['ready']
    assert import_exports(root, [b])['replayed_conversations'] == 1
    assert check_readiness(root)['ready']


@pytest.mark.parametrize('after_write', [False, True])
def test_cli_reports_partial_progress_and_retry_is_exact(tmp_path, monkeypatch, capsys, after_write):
    from core.sources.chatgpt_import import main
    root = tmp_path / 'corpus'
    source = export(tmp_path / 'a.json', [conversation('c1'), conversation('c2')])
    real = FilesystemInformationWrites.create
    calls = 0
    def fail_second(self, *args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            if after_write:
                real(self, *args, **kwargs)
            raise OSError('synthetic publication failure')
        return real(self, *args, **kwargs)
    monkeypatch.setattr(FilesystemInformationWrites, 'create', fail_second)
    assert main(['--root', str(root), str(source)]) == 1
    blocked = json.loads(capsys.readouterr().out)
    assert blocked['status'] == 'BLOCKED'
    assert blocked['progress'] == dict(new_conversations=1, replayed_conversations=0,
        new_originals=1, publication_attempted=True)
    monkeypatch.setattr(FilesystemInformationWrites, 'create', real)
    result = import_exports(root, [source])
    assert result['replayed_conversations'] == (2 if after_write else 1)
    assert result['new_conversations'] == (0 if after_write else 1)
    assert check_readiness(root)['ready']
    before = files(root)
    import_exports(root, [source])
    assert files(root) == before
