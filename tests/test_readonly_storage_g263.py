# ==========================================================
# Projet      : Eidolon Memory Engine
# Organisation: Eidolon Core Technologies (ECT)
# Fichier     : tests/test_readonly_storage_g263.py
# Description : Existing-inode read-only recall and cross-process exclusion.
# Standard    : Eidolon Presentation Standard v1
# ==========================================================
"""Synthetic local storage only; no deployment or mount qualification implied."""
import errno
import os
from pathlib import Path
import subprocess
import sys

import pytest

from core import persistence
from core.backend.filesystem import FilesystemBackend
from core.retrieval.contextual import ContextualRecall
from services.memory_bridge import build_recall
from tests.test_contextual_recall import backend, store
from tests.test_migration_converter import fingerprints
from tests.test_routing_execution import seed, preview, execute, STAMP

pytestmark = pytest.mark.skipif(not sys.platform.startswith('linux'), reason='Linux local flock contract')


def deny_writes(monkeypatch, root):
    """Inject EROFS for write opens and mkdir, even if directories exist."""
    path_open, os_open, mkdir = Path.open, os.open, Path.mkdir
    def inside(path):
        return isinstance(path, (str, bytes, os.PathLike)) and Path(os.fsdecode(path)).absolute().is_relative_to(root)
    def readonly_open(path, mode='r', *args, **kwargs):
        if inside(path) and any(c in mode for c in 'wa+x'):
            raise OSError(errno.EROFS, 'synthetic read-only storage')
        return path_open(path, mode, *args, **kwargs)
    def readonly_os_open(path, flags, *args, **kwargs):
        if inside(path) and flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND):
            raise OSError(errno.EROFS, 'synthetic read-only storage')
        return os_open(path, flags, *args, **kwargs)
    def readonly_mkdir(path, *args, **kwargs):
        if inside(path):
            raise OSError(errno.EROFS, 'synthetic read-only storage')
        return mkdir(path, *args, **kwargs)
    monkeypatch.setattr(Path, 'open', readonly_open)
    monkeypatch.setattr(os, 'open', readonly_os_open)
    monkeypatch.setattr(Path, 'mkdir', readonly_mkdir)


@pytest.mark.parametrize('project', [False, True])
def test_construct_and_recall_without_any_write_open_or_mkdir(tmp_path, monkeypatch, project):
    if project:
        data, executor, memory = seed(tmp_path)
        execute(executor, preview(executor, memory))
        options = dict(project_id='project', query_scope={'goal': 'efficiency'}, at=STAMP)
        query, expected = 'measure', 'second'
    else:
        data = backend(tmp_path)
        store(data, 'sample')
        options, query, expected = {}, 'power', 'sample'
    before = fingerprints(tmp_path)
    deny_writes(monkeypatch, tmp_path)
    # Before the fix, even a pre-existing lock uses a+b and fails.
    with pytest.raises(OSError) as error:
        ContextualRecall(data).recall(query, **options)
    assert error.value.errno == errno.EROFS
    reader = build_recall(tmp_path, read_only_storage=True)
    result = reader.recall(query, **options)
    assert [item.information_id for item in result.items] == [expected]
    if project:
        assert result.dossier_status == 'CURRENT'
    assert fingerprints(tmp_path) == before


@pytest.mark.parametrize('missing', ['persistent', 'pending-delete', 'persistent-lock', 'threads-lock'])
def test_missing_prerequisite_refused_without_provisioning(tmp_path, missing):
    data = backend(tmp_path)
    store(data, 'sample')
    if missing == 'persistent':
        for path in data.persistent_root.iterdir():
            path.unlink()
        data.persistent_root.rmdir()
    elif missing == 'pending-delete':
        data.pending_delete_root.rmdir()
    elif missing == 'persistent-lock':
        (data.persistent_root / '.write.lock').unlink()
    else:
        (data.persistent_root / 'threads').mkdir()
    before = fingerprints(tmp_path)
    with pytest.raises((ValueError, FileNotFoundError)):
        build_recall(tmp_path, read_only_storage=True)
    assert fingerprints(tmp_path) == before


@pytest.mark.parametrize('kind', ['symlink', 'directory', 'fifo'])
def test_readonly_lock_rejects_nonregular_files(tmp_path, kind):
    lock = tmp_path / '.write.lock'
    if kind == 'symlink':
        target = tmp_path / 'target'
        target.touch()
        lock.symlink_to(target)
    elif kind == 'directory':
        lock.mkdir()
    else:
        os.mkfifo(lock)
    with pytest.raises((ValueError, OSError)):
        with persistence.exclusive_write(tmp_path, read_only=True, blocking=False):
            pytest.fail('invalid lock acquired')


def test_replacement_while_acquiring_is_refused(tmp_path, monkeypatch):
    import fcntl
    lock = tmp_path / '.write.lock'
    lock.touch()
    real_flock = fcntl.flock
    def replace_after_acquire(fd, operation):
        real_flock(fd, operation)
        if operation & fcntl.LOCK_EX:
            lock.rename(tmp_path / 'old-lock')
            lock.touch()
    monkeypatch.setattr(fcntl, 'flock', replace_after_acquire)
    with pytest.raises(ValueError, match='same regular file'):
        with persistence.exclusive_write(tmp_path, read_only=True):
            pytest.fail('read under obsolete lock')
    assert not persistence.write_lock_held(tmp_path)


CHILD = '''
import sys
from pathlib import Path
from core.persistence import exclusive_write, RepositoryBusy
try:
    with exclusive_write(Path(sys.argv[1]), read_only=sys.argv[2] == 'True', blocking=False):
        print('ACQUIRED')
except RepositoryBusy:
    print('BUSY')
'''


def child_lock(root, readonly):
    result = subprocess.run([sys.executable, '-c', CHILD, str(root), str(readonly)],
                            cwd=Path(__file__).resolve().parents[1], capture_output=True,
                            text=True, timeout=10, check=True)
    return result.stdout.strip()


@pytest.mark.parametrize('parent_readonly,child_readonly', [(True, False), (False, True), (True, True)])
def test_same_inode_excludes_an_independent_process_and_survives_restart(tmp_path, parent_readonly, child_readonly):
    lock = tmp_path / '.write.lock'
    lock.write_bytes(b'stable')
    identity = (lock.stat().st_dev, lock.stat().st_ino)
    with persistence.exclusive_write(tmp_path, read_only=parent_readonly):
        assert child_lock(tmp_path, child_readonly) == 'BUSY'
    assert child_lock(tmp_path, child_readonly) == 'ACQUIRED'
    assert child_lock(tmp_path, child_readonly) == 'ACQUIRED'
    assert (lock.stat().st_dev, lock.stat().st_ino) == identity
    assert lock.read_bytes() == b'stable'


def test_reentrant_readonly_cannot_promote_to_writer_and_releases_after_error(tmp_path):
    (tmp_path / '.write.lock').touch()
    with pytest.raises(RuntimeError, match='stop'):
        with persistence.exclusive_write(tmp_path, read_only=True):
            with persistence.exclusive_write(tmp_path, read_only=True):
                assert persistence.write_lock_held(tmp_path)
            with pytest.raises(ValueError, match='promote'):
                with persistence.exclusive_write(tmp_path):
                    pytest.fail('promoted')
            raise RuntimeError('stop')
    assert not persistence.write_lock_held(tmp_path)
    assert child_lock(tmp_path, False) == 'ACQUIRED'


@pytest.mark.parametrize('option', [None, 1, 'yes'])
def test_strict_boolean_options(tmp_path, option):
    with pytest.raises(ValueError):
        with persistence.exclusive_write(tmp_path, read_only=option):
            pass
    with pytest.raises(ValueError):
        build_recall(tmp_path, read_only_storage=option)
    with pytest.raises(ValueError):
        FilesystemBackend(tmp_path, tmp_path, create_directories=option)
    with pytest.raises(ValueError):
        ContextualRecall(None, read_only_locks=option)


def test_no_implicit_roots_when_provisioning_disabled():
    with pytest.raises(ValueError, match='explicit roots'):
        FilesystemBackend(create_directories=False)


def test_unsupported_platform_refuses_without_writable_fallback(tmp_path, monkeypatch):
    monkeypatch.setattr(persistence.sys, 'platform', 'win32')
    with pytest.raises(NotImplementedError, match='Linux'):
        with persistence.exclusive_write(tmp_path, read_only=True):
            pass
    with pytest.raises(NotImplementedError):
        ContextualRecall(None, read_only_locks=True)
    assert not list(tmp_path.iterdir())


def test_readonly_recall_with_real_nonroot_permissions(tmp_path):
    if os.geteuid() == 0:
        pytest.skip('real DAC refusal requires ordinary UID; covered in CI')
    data = backend(tmp_path)
    store(data, 'sample')
    paths = [tmp_path, *tmp_path.rglob('*')]
    modes = {p: p.stat().st_mode & 0o777 for p in paths}
    try:
        for p in paths:
            p.chmod(0o500 if p.is_dir() else 0o400)
        with pytest.raises(PermissionError):
            ContextualRecall(data).recall('power')
        assert build_recall(tmp_path, read_only_storage=True).recall('power').items[0].information_id == 'sample'
    finally:
        for p in paths:
            p.chmod(modes[p])


def test_bridge_cli_refuses_missing_lock_before_listening(tmp_path, monkeypatch):
    from services import memory_bridge
    backend(tmp_path)  # no lock yet
    monkeypatch.setenv('EIDOLON_MEMORY_BRIDGE_TOKEN', 's' * 32)
    monkeypatch.setattr(sys, 'argv', ['bridge', '--root', str(tmp_path), '--read-only-storage'])
    def no_server(*args, **kwargs):
        pytest.fail('server bound before storage validation')
    monkeypatch.setattr(memory_bridge, 'BoundedRecallServer', no_server)
    with pytest.raises(SystemExit) as error:
        memory_bridge.main()
    assert error.value.code == 2
    assert not (tmp_path / 'memory/persistent/.write.lock').exists()


def test_real_http_recall_and_missing_lock_fail_closed(tmp_path, monkeypatch):
    import json
    from tests.test_memory_bridge_limits_g245 import request, server
    data = backend(tmp_path)
    store(data, 'sample')
    deny_writes(monkeypatch, tmp_path)
    with server(build_recall(tmp_path, read_only_storage=True), timeout=2) as (httpd, _):
        code, body = request(httpd)
        assert code == 200
        assert json.loads(body)['result']['items'][0]['information_id'] == 'sample'
        (data.persistent_root / '.write.lock').unlink()  # noncooperating fault injection
        code, body = request(httpd)
        assert code == 503 and json.loads(body) == {'error': 'RECALL_UNAVAILABLE'}
    assert not (data.persistent_root / '.write.lock').exists()


@pytest.mark.parametrize('target', ['root', 'ancestor'])
def test_linked_storage_path_refused(tmp_path, target):
    data = backend(tmp_path)
    store(data, 'sample')
    alias = tmp_path / 'alias'
    alias.symlink_to(tmp_path, target_is_directory=True)
    root = alias if target == 'root' else alias / 'child'
    with pytest.raises(ValueError, match='symlink'):
        build_recall(root, read_only_storage=True)


def test_busy_preflight_refuses_without_waiting(tmp_path):
    data = backend(tmp_path)
    store(data, 'sample')
    script = '''
import sys
from pathlib import Path
from core.persistence import RepositoryBusy
from services.memory_bridge import build_recall
try:
    build_recall(Path(sys.argv[1]), read_only_storage=True)
except RepositoryBusy:
    print('BUSY')
'''
    with persistence.exclusive_write(data.persistent_root):
        result = subprocess.run([sys.executable, '-c', script, str(tmp_path)],
                                capture_output=True, text=True, check=True, timeout=10)
    assert result.stdout.strip() == 'BUSY'


def test_cli_passes_explicit_mode_to_reader(tmp_path, monkeypatch):
    from services import memory_bridge
    data = backend(tmp_path)
    store(data, 'sample')
    monkeypatch.setenv('EIDOLON_MEMORY_BRIDGE_TOKEN', 's' * 32)
    monkeypatch.setattr(sys, 'argv', ['bridge', '--root', str(tmp_path), '--read-only-storage'])
    seen = []
    real_build = memory_bridge.build_recall
    def capture(*args, **kwargs):
        recall = real_build(*args, **kwargs)
        seen.append(recall.read_only_locks)
        return recall
    class Server:
        def __init__(self, address, handler):
            assert seen == [True]
        def serve_forever(self):
            seen.append('served')
        def server_close(self):
            seen.append('closed')
    monkeypatch.setattr(memory_bridge, 'build_recall', capture)
    monkeypatch.setattr(memory_bridge, 'BoundedRecallServer', Server)
    deny_writes(monkeypatch, tmp_path)
    memory_bridge.main()
    assert seen == [True, 'served', 'closed']
