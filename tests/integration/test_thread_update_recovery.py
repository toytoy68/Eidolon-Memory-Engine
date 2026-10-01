"""Real process exits and competing project writers, without Manager sockets."""
import json
import multiprocessing
import os
from pathlib import Path

import pytest

from core.backend.filesystem import FilesystemBackend
from core.backend.errors import InformationDeletionBlocked
from core.operations.errors import OperationConflict
from core.operations.readiness import recover_all
from core.operations.thread_update import FilesystemThreadUpdates
from core.threads.storage import ThreadStorageError
from tests.test_thread_updates import seed, execute


def crash_worker(root, boundary):
    root = Path(root)
    writer = FilesystemThreadUpdates(FilesystemBackend(root / 'memory/persistent', root / 'memory/history'))
    if boundary == 'before_thread':
        writer.storage._update_coordinated = lambda *args: os._exit(74)
    else:
        writer.events.save = lambda event: os._exit(74)
    execute(writer, {'kind': 'LINK', 'information_id': 'two'})


@pytest.mark.parametrize('boundary', ['before_thread', 'after_thread'])
def test_process_exit_releases_locks_and_global_recovery_finishes(tmp_path, boundary):
    backend, writer = seed(tmp_path)
    context = multiprocessing.get_context('spawn')
    child = context.Process(target=crash_worker, args=(str(tmp_path), boundary))
    child.start()
    try:
        child.join(15)
        assert child.exitcode == 74
    finally:
        if child.is_alive():
            child.terminate()
            child.join()
    assert recover_all(tmp_path)['readiness']['ready']
    assert writer.storage._concerns(writer.storage.get('project')) == {'one', 'two'}
    assert writer.storage.get('project').revision == 2
    assert len(list(writer.events.events_root.glob('*.md'))) == 1


def competing_worker(root, slot, mode, ready, start):
    root = Path(root)
    backend = FilesystemBackend(root / 'memory/persistent', root / 'memory/history')
    writer = FilesystemThreadUpdates(backend)
    ready.set()
    if not start.wait(10):
        raise RuntimeError('start timeout')
    try:
        if mode == 'delete' and slot == 1:
            backend.delete_request('two', 'human', 'test', 1, 'delete-two')
            backend.approve_delete('two', 'delete-two')
            outcome = 'DELETED'
        else:
            opid = 'same' if mode == 'same' else 'op-' + str(slot)
            execute(writer, {'kind': 'LINK', 'information_id': 'two'}, opid=opid)
            outcome = 'LINKED'
    except (OperationConflict, ThreadStorageError, InformationDeletionBlocked):
        outcome = 'BLOCKED'
    (root / f'outcome-{slot}.json').write_text(json.dumps(outcome))


@pytest.mark.parametrize('mode', ['same', 'different', 'delete'])
def test_concurrent_link_replay_and_information_deletion(tmp_path, mode):
    backend, writer = seed(tmp_path)
    context = multiprocessing.get_context('spawn')
    start = context.Event()
    ready = [context.Event(), context.Event()]
    children = [context.Process(target=competing_worker, args=(str(tmp_path), slot, mode, ready[slot], start))
                for slot in range(2)]
    try:
        for child in children:
            child.start()
        assert all(event.wait(10) for event in ready)
        start.set()
        for child in children:
            child.join(15)
            assert child.exitcode == 0
    finally:
        for child in children:
            if child.is_alive():
                child.terminate()
                child.join()
    outcomes = sorted(json.loads((tmp_path / f'outcome-{slot}.json').read_text()) for slot in range(2))
    if mode != 'delete':
        assert outcomes == (['LINKED', 'LINKED'] if mode == 'same' else ['BLOCKED', 'LINKED'])
    thread = writer.storage.get('project')
    if mode == 'delete':
        assert outcomes in (['BLOCKED', 'LINKED'], ['BLOCKED', 'DELETED'])
        assert ('two' in writer.storage._concerns(thread)) == (backend.get('two') is not None)
    else:
        assert thread.revision == 2
        assert len(list(writer.events.events_root.glob('*.md'))) == 1
