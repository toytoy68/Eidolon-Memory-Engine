"""Abrupt process death is not a simulated exception or storage power loss."""
import multiprocessing
import os
from dataclasses import replace
from pathlib import Path

import pytest

from core.backend.filesystem import FilesystemBackend
from core.backend.models import Memory
from core.information.writes import FilesystemInformationWrites


def crash_worker(root, kind, phase):
    root = Path(root)
    writer = FilesystemInformationWrites(FilesystemBackend(root / 'memory/persistent', root / 'memory/history'))
    target = Memory('info-1', content='original', metadata={'epistemic_status': 'CONFIRMED'})
    kwargs = dict(operation_id='op', event_id='event', actor='test', timestamp='fixed')
    if kind == 'update':
        writer.create(target, **(kwargs | {'operation_id': 'initial', 'event_id': 'initial-event'}))
        target = replace(target, content='updated')
    obj, attr = {
        'prepared': (writer.operations, 'create'), 'applying': (writer.operations, 'update'),
        'memory': (writer.backend, '_atomic_write'), 'event': (writer.events, 'save'),
        'committed': (writer.operations, 'update'),
    }[phase]
    real = getattr(obj, attr)
    def interrupted(*args, **kw):
        result = real(*args, **kw)
        if phase not in {'applying', 'committed'} or args[0].status.value == phase.upper():
            os._exit(74)
        return result
    setattr(obj, attr, interrupted)
    if kind == 'update':
        writer.update(target, previous_revision=1, **kwargs)
    else:
        writer.create(target, **kwargs)
    os._exit(75)


@pytest.mark.parametrize('kind', ['create', 'update'])
@pytest.mark.parametrize('phase', ['prepared', 'applying', 'memory', 'event', 'committed'])
def test_restart_after_process_death(tmp_path, kind, phase):
    process = multiprocessing.get_context('spawn').Process(target=crash_worker, args=(str(tmp_path), kind, phase))
    process.start()
    process.join(15)
    if process.is_alive():
        process.terminate()
        process.join()
        pytest.fail('Information write deadlocked')
    assert process.exitcode == 74
    writer = FilesystemInformationWrites(FilesystemBackend(tmp_path / 'memory/persistent', tmp_path / 'memory/history'))
    assert writer.recover()['op']['status'] == 'COMMITTED'
    expected = 2 if kind == 'update' else 1
    target = writer.backend.get('info-1')
    assert target.revision == expected
    assert target.content == ('updated' if kind == 'update' else 'original')
    assert len(list(writer.events.events_root.glob('*.md'))) == expected
    assert writer.recover()['op']['status'] == 'COMMITTED'
