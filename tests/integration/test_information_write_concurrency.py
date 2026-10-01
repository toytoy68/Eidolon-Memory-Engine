"""Information concurrency using shared Events, without a Manager server."""
import json
import multiprocessing
from pathlib import Path

import pytest

from core.backend.filesystem import FilesystemBackend
from core.backend.models import Memory
from core.information.writes import FilesystemInformationWrites
from core.operations.errors import OperationConflict


def write_worker(root, slot, same_command, ready, start):
    root = Path(root)
    writer = FilesystemInformationWrites(FilesystemBackend(root / 'memory/persistent', root / 'memory/history'))
    ready.set()
    if not start.wait(10):
        raise RuntimeError('test start timeout')
    opid = 'same' if same_command else f'op-{slot}'
    try:
        result = writer.update(Memory('info-1', content='updated'), previous_revision=1,
                               operation_id=opid, event_id='event-' + opid, actor='human', timestamp='fixed')
        outcome = {'status': 'OK', 'result': result}
    except OperationConflict:
        outcome = {'status': 'CONFLICT'}
    (root / f'worker-{slot}.json').write_text(json.dumps(outcome))


@pytest.mark.parametrize('same_command', [False, True])
def test_two_information_writers(tmp_path, same_command):
    backend = FilesystemBackend(tmp_path / 'memory/persistent', tmp_path / 'memory/history')
    backend.store(Memory('info-1', content='initial'))
    context = multiprocessing.get_context('spawn')
    start = context.Event()
    ready = [context.Event(), context.Event()]
    processes = [context.Process(target=write_worker, args=(str(tmp_path), i, same_command, ready[i], start))
                 for i in range(2)]
    try:
        for process in processes:
            process.start()
        assert all(event.wait(10) for event in ready)
        start.set()
        for process in processes:
            process.join(15)
            assert process.exitcode == 0
    finally:
        for process in processes:
            if process.is_alive():
                process.terminate()
                process.join()
    outcomes = [json.loads((tmp_path / f'worker-{i}.json').read_text()) for i in range(2)]
    assert sorted(o['status'] for o in outcomes) == (['OK', 'OK'] if same_command else ['CONFLICT', 'OK'])
    writer = FilesystemInformationWrites(backend)
    assert backend.get('info-1').revision == 2
    assert len(list(writer.events.events_root.glob('*.md'))) == 1
    if same_command:
        assert outcomes[0]['result'] == outcomes[1]['result']
