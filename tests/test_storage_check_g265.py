# ==========================================================
# Projet      : Eidolon Memory Engine
# Organisation: Eidolon Core Technologies (ECT)
# Fichier     : tests/test_storage_check_g265.py
# Description : One-shot storage diagnostics, lock scope and safe CLI output.
# Standard    : Eidolon Presentation Standard v1
# ==========================================================
"""Synthetic corpus; real subprocess CLI/locks, injected read-only failures."""
import builtins
import json
import os
from pathlib import Path
import socket
import subprocess
import sys

import pytest

from core import persistence
from services import memory_bridge as bridge
from tests.test_contextual_recall import backend, store
from tests.test_migration_converter import fingerprints
from tests.test_readonly_storage_g263 import child_lock, deny_writes
from tests.test_routing_execution import seed, preview, execute

pytestmark = pytest.mark.skipif(not sys.platform.startswith('linux'), reason='Linux readonly storage contract')
ROOT = Path(__file__).resolve().parents[1]


def check_cli(root, *args):
    env = os.environ.copy()
    env.pop('EIDOLON_MEMORY_BRIDGE_TOKEN', None)
    return subprocess.run([sys.executable, '-B', '-m', 'services.memory_bridge',
                           '--root', str(root), '--check-storage', *args],
                          cwd=ROOT, env=env, capture_output=True, text=True, timeout=10)


def assert_report(result, state):
    assert result.returncode == bridge.STORAGE_CHECK_EXIT[state], result.stderr
    assert result.stderr == ''
    report = json.loads(result.stdout)
    assert report['schema'] == 'eidolon-memory-storage-check/1'
    assert report['state'] == state
    assert report['scope'] == 'canonical_storage_only'
    assert report['read_only_locks'] is True
    assert len(result.stdout.splitlines()) == 1
    return report


def test_real_cli_ready_without_secret_and_without_storage_mutation(tmp_path):
    data = backend(tmp_path)
    store(data, 'sample')
    before = fingerprints(tmp_path)
    report = assert_report(check_cli(tmp_path), 'READY')
    assert report['issues'] == 0
    assert fingerprints(tmp_path) == before


def test_check_skips_token_model_and_network_and_never_provisions(tmp_path, monkeypatch, capsys):
    data = backend(tmp_path)
    store(data, 'sample')
    original_import = builtins.__import__
    def checked_import(name, *args, **kwargs):
        assert name.split('.')[0] not in {'torch', 'sentence_transformers'}
        return original_import(name, *args, **kwargs)
    def no_network(*args, **kwargs):
        pytest.fail('network opened during storage-only check')
    monkeypatch.setattr(builtins, '__import__', checked_import)
    monkeypatch.setattr(socket, 'socket', no_network)
    monkeypatch.setattr(bridge, 'BoundedRecallServer', no_network)
    monkeypatch.setenv('EIDOLON_MEMORY_BRIDGE_TOKEN', 'invalid token')
    monkeypatch.setattr(sys, 'argv', ['bridge', '--root', str(tmp_path), '--check-storage'])
    deny_writes(monkeypatch, tmp_path)
    assert bridge.main() == 0
    assert json.loads(capsys.readouterr().out)['state'] == 'READY'


@pytest.mark.parametrize('missing', ['root', 'lock', 'pending'])
def test_missing_storage_returns_unavailable_and_creates_nothing(tmp_path, missing):
    root = tmp_path / 'absent' if missing == 'root' else tmp_path
    if missing != 'root':
        data = backend(root)
        if missing == 'pending':
            data.pending_delete_root.rmdir()
    before = fingerprints(tmp_path)
    assert_report(check_cli(root), 'UNAVAILABLE')
    assert fingerprints(tmp_path) == before


@pytest.mark.parametrize('lock_root', ['persistent', 'threads'])
def test_busy_reports_immediately_from_independent_process_and_recovers(tmp_path, lock_root):
    data, _, _ = seed(tmp_path)
    root = data.persistent_root if lock_root == 'persistent' else data.persistent_root / 'threads'
    before = fingerprints(tmp_path)
    with persistence.exclusive_write(root):
        # CLI timeout is the bound; the holder cannot release until CLI returns.
        assert_report(check_cli(tmp_path), 'BUSY')
    assert_report(check_cli(tmp_path), 'READY')
    assert fingerprints(tmp_path) == before


def test_readiness_runs_with_both_locks_held_and_releases_them(tmp_path, monkeypatch):
    data, _, _ = seed(tmp_path)
    real_check = bridge.check_readiness
    called = []
    def inspect(root):
        for path in (data.persistent_root, data.persistent_root / 'threads'):
            assert child_lock(path, False) == 'BUSY'
        called.append(root)
        return real_check(root)
    monkeypatch.setattr(bridge, 'check_readiness', inspect)
    assert bridge.check_storage(tmp_path)['state'] == 'READY'
    assert called == [tmp_path]
    for path in (data.persistent_root, data.persistent_root / 'threads'):
        assert child_lock(path, False) == 'ACQUIRED'


def test_incomplete_operation_blocks_without_recovery_or_sensitive_output(tmp_path, monkeypatch):
    data, executor, memory = seed(tmp_path)
    prepared = preview(executor, memory)
    def stop(stage):
        if stage == 'after_information':
            raise RuntimeError('synthetic interruption')
    monkeypatch.setattr(executor, '_checkpoint', stop)
    with pytest.raises(RuntimeError):
        execute(executor, prepared)
    before = fingerprints(tmp_path)
    result = check_cli(tmp_path)
    report = assert_report(result, 'BLOCKED')
    assert report['issues'] > 0
    assert 'intent' not in result.stdout and 'measure' not in result.stdout
    assert str(tmp_path) not in result.stdout
    assert fingerprints(tmp_path) == before


def test_corrupt_canonical_content_is_blocked_without_echo(tmp_path):
    data = backend(tmp_path)
    store(data, 'sample')
    (data.persistent_root / 'sample.md').write_text('PRIVATE-CORRUPT-SENTINEL')
    before = fingerprints(tmp_path)
    result = check_cli(tmp_path)
    assert_report(result, 'BLOCKED')
    assert 'PRIVATE' not in result.stdout and 'sample' not in result.stdout
    assert fingerprints(tmp_path) == before


def test_missing_lock_between_preflight_and_scan_cannot_pass(tmp_path, monkeypatch):
    data = backend(tmp_path)
    store(data, 'sample')
    real_build = bridge.build_recall
    def lose_lock(*args, **kwargs):
        reader = real_build(*args, **kwargs)
        (data.persistent_root / '.write.lock').unlink()
        return reader
    monkeypatch.setattr(bridge, 'build_recall', lose_lock)
    assert bridge.check_storage(tmp_path)['state'] == 'UNAVAILABLE'
    assert not (data.persistent_root / '.write.lock').exists()


@pytest.mark.parametrize('error,state', [(PermissionError('PRIVATE-PATH'), 'UNAVAILABLE'),
                                        (RuntimeError('PRIVATE-RECORD'), 'ERROR')])
def test_scan_exception_is_sanitized_and_locks_released(tmp_path, monkeypatch, error, state):
    data, _, _ = seed(tmp_path)
    def fail(root):
        raise error
    monkeypatch.setattr(bridge, 'check_readiness', fail)
    result = bridge.check_storage(tmp_path)
    assert result['state'] == state
    assert result['issues'] is None
    assert 'PRIVATE' not in json.dumps(result)
    for path in (data.persistent_root, data.persistent_root / 'threads'):
        assert child_lock(path, False) == 'ACQUIRED'


def test_platform_refusal_before_storage_probe(tmp_path, monkeypatch):
    monkeypatch.setattr(persistence.sys, 'platform', 'win32')
    def no_probe(*args, **kwargs):
        pytest.fail('storage touched on unsupported platform')
    monkeypatch.setattr(bridge, 'build_recall', no_probe)
    assert bridge.check_storage(tmp_path)['state'] == 'UNSUPPORTED'
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize('args', [('--port', '18765'), ('--reranker-cache', '/unused')])
def test_check_rejects_server_only_arguments(tmp_path, args):
    result = check_cli(tmp_path, *args)
    assert result.returncode == 64 and result.stdout == ''  # G268: usage, not BLOCKED
    assert 'cannot be combined' in result.stderr
    assert list(tmp_path.iterdir()) == []


def test_serve_still_requires_token(tmp_path, monkeypatch):
    monkeypatch.delenv('EIDOLON_MEMORY_BRIDGE_TOKEN', raising=False)
    monkeypatch.setattr(sys, 'argv', ['bridge', '--root', str(tmp_path)])
    with pytest.raises(SystemExit) as error:
        bridge.main()
    assert error.value.code == 2
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize('value', [0, 1, None, 'no'])
def test_snapshot_rejects_nonboolean_blocking(tmp_path, value):
    data = backend(tmp_path)
    reader = bridge.ContextualRecall(data)
    with pytest.raises(ValueError, match='boolean'):
        with reader.storage_snapshot(blocking=value):
            pytest.fail('invalid option accepted')
    assert not (data.persistent_root / '.write.lock').exists()


def test_symlinked_root_refused_without_private_path_in_json(tmp_path):
    data = backend(tmp_path)
    store(data, 'sample')
    alias = tmp_path / 'PRIVATE-ALIAS'
    alias.symlink_to(tmp_path, target_is_directory=True)
    result = check_cli(alias)
    assert_report(result, 'UNAVAILABLE')
    assert 'PRIVATE' not in result.stdout
