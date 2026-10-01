"""Abrupt process exits across receipt publication and durable plan retirement."""
import multiprocessing
import os
from pathlib import Path

import pytest

from core.backend.filesystem import FilesystemBackend
from core.backend.models import Memory
from core.information.writes import FilesystemInformationWrites
from core.information.write_audit import audit_information_writes


def crash_compaction(root, phase):
    from core.information import compaction
    root = Path(root)
    writer = FilesystemInformationWrites(FilesystemBackend(root / 'memory/persistent', root / 'memory/history'))
    writer.create(Memory('info-1', content='private'), operation_id='create', event_id='created', actor='human', timestamp='fixed')
    if phase == 'published':
        real = compaction.atomic_write_text
        def interrupted(*args):
            real(*args)
            os._exit(74)
        compaction.atomic_write_text = interrupted
    elif phase == 'removed':
        real = Path.unlink
        def interrupted(path, *args, **kwargs):
            real(path, *args, **kwargs)
            if path == writer.operations._path('create'):
                os._exit(74)
        Path.unlink = interrupted
    else:
        real = compaction.durable_unlink
        def interrupted(*args):
            real(*args)
            os._exit(74)
        compaction.durable_unlink = interrupted
    writer.compact('create')
    os._exit(75)


@pytest.mark.parametrize('phase', ['published', 'removed', 'synced'])
def test_compaction_process_crash_and_replay(tmp_path, phase):
    process = multiprocessing.get_context('spawn').Process(target=crash_compaction, args=(str(tmp_path), phase))
    process.start()
    process.join(15)
    if process.is_alive():
        process.terminate()
        process.join()
        pytest.fail('compaction deadlocked')
    assert process.exitcode == 74
    writer = FilesystemInformationWrites(FilesystemBackend(tmp_path / 'memory/persistent', tmp_path / 'memory/history'))
    result = writer.compact('create')
    assert result['revision'] == 1
    assert not writer.operations._path('create').exists()
    assert audit_information_writes(tmp_path)['issues'] == []
    writer.backend.delete_request('info-1', 'human', 'obsolete', 1, 'delete')
    writer.backend.approve_delete('info-1', 'delete')
    assert writer.create(Memory('info-1', content='private'), operation_id='create', event_id='created', actor='human', timestamp='fixed') == result
    assert writer.backend.get('info-1') is None
