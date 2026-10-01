"""Routing intentions survive actual process exits and concurrent retries."""
import json
import multiprocessing
import os
from pathlib import Path

import pytest

from core.backend.filesystem import FilesystemBackend
from core.operations.errors import OperationConflict
from core.operations.readiness import recover_all
from core.routing.execution import RoutingExecutor
from tests.test_routing_execution import seed, preview, execute


def crash(root, prepared, boundary):
    root = Path(root)
    executor = RoutingExecutor(FilesystemBackend(root / 'memory/persistent', root / 'memory/history'))
    def checkpoint(stage):
        if stage == boundary:
            os._exit(74)
    executor._checkpoint = checkpoint
    execute(executor, prepared)


@pytest.mark.parametrize('boundary', ['before_information', 'after_information', 'after_project', 'after_projection'])
def test_process_crash_recovers_complete_journey(tmp_path, boundary):
    backend, executor, memory = seed(tmp_path)
    prepared = preview(executor, memory)
    child = multiprocessing.get_context('spawn').Process(target=crash, args=(str(tmp_path), prepared, boundary))
    child.start()
    try:
        child.join(15)
        assert child.exitcode == 74
    finally:
        if child.is_alive():
            child.terminate()
            child.join()
    assert recover_all(tmp_path)['readiness']['ready']
    assert backend.get('second') == memory
    assert executor.storage.get('project').revision == 2
    assert executor.dossiers.status('project')['status'] == 'CURRENT'


def competitor(root, prepared, intent, slot, ready, start):
    root = Path(root)
    executor = RoutingExecutor(FilesystemBackend(root / 'memory/persistent', root / 'memory/history'))
    ready.set()
    if not start.wait(10):
        raise RuntimeError('start timeout')
    try:
        result = {'status': 'OK', 'result': execute(executor, prepared, intent)}
    except OperationConflict:
        result = {'status': 'CONFLICT'}
    (root / f'worker-{slot}.json').write_text(json.dumps(result))


@pytest.mark.parametrize('same_intent', [True, False])
def test_concurrent_intentions_do_not_duplicate_information_or_project(tmp_path, same_intent):
    backend, executor, memory = seed(tmp_path)
    prepared = preview(executor, memory)
    context = multiprocessing.get_context('spawn')
    start = context.Event()
    ready = [context.Event(), context.Event()]
    children = [context.Process(target=competitor, args=(str(tmp_path), prepared,
                'same' if same_intent else f'intent-{slot}', slot, ready[slot], start)) for slot in range(2)]
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
    outcomes = [json.loads((tmp_path / f'worker-{slot}.json').read_text()) for slot in range(2)]
    assert sorted(item['status'] for item in outcomes) == (['OK', 'OK'] if same_intent else ['CONFLICT', 'OK'])
    if same_intent:
        assert outcomes[0] == outcomes[1]
    assert executor.storage.get('project').revision == 2
    assert len(executor.storage.list()) == 1
    assert backend.get('second') == memory
