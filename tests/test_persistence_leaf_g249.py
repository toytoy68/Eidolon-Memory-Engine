# ==========================================================
# Projet      : Eidolon Memory Engine
# Organisation: Eidolon Core Technologies (ECT)
# Fichier     : tests/test_persistence_leaf_g249.py
# Description : Preserve byte publication and shared phase state across extraction.
# Standard    : Eidolon Presentation Standard v1
# ==========================================================
import os
from pathlib import Path
import stat

import pytest

from core import persistence
from core.migration import converter


def writer():
    return getattr(persistence, 'atomic_write_bytes', converter._atomic_bytes)


def test_legacy_byte_writer_is_the_public_persistence_function():
    assert converter._atomic_bytes is persistence.atomic_write_bytes


def test_read_phase_and_publisher_share_exactly_one_context_variable():
    from core.operations import publication_phase, read_phase
    assert read_phase._phase is publication_phase._phase
    assert read_phase.invalidate_publication is publication_phase.invalidate_publication


def test_byte_publication_flushes_file_before_rename_and_directory_after(tmp_path, monkeypatch):
    path = tmp_path / 'output'
    path.write_bytes(b'old')
    events = []
    real_sync, real_replace = os.fsync, os.replace
    def sync(fd):
        events.append('directory' if stat.S_ISDIR(os.fstat(fd).st_mode) else 'file')
        return real_sync(fd)
    def replace(source, destination):
        assert path.read_bytes() == b'old'
        events.append('replace')
        return real_replace(source, destination)
    monkeypatch.setattr(os, 'fsync', sync)
    monkeypatch.setattr(os, 'replace', replace)
    writer()(path, b'new\x00\xff')
    assert path.read_bytes() == b'new\x00\xff'
    assert events == ['file', 'replace', 'directory']
    assert list(tmp_path.iterdir()) == [path]


def test_failed_rename_keeps_original_and_removes_temporary(tmp_path, monkeypatch):
    path = tmp_path / 'output'
    path.write_bytes(b'old')
    def fail(*args):
        raise OSError('synthetic rename failure')
    monkeypatch.setattr(os, 'replace', fail)
    with pytest.raises(OSError):
        writer()(path, b'new')
    assert path.read_bytes() == b'old'
    assert list(tmp_path.iterdir()) == [path]


def test_directory_flush_failure_never_claims_rollback(tmp_path, monkeypatch):
    path = tmp_path / 'output'
    path.write_bytes(b'old')
    original = os.fsync
    def fail(fd):
        if stat.S_ISDIR(os.fstat(fd).st_mode):
            raise OSError('synthetic directory flush failure')
        return original(fd)
    monkeypatch.setattr(os, 'fsync', fail)
    with pytest.raises(OSError):
        writer()(path, b'new')
    assert path.read_bytes() == b'new'  # effect happened; durability remains unknown
    assert list(tmp_path.iterdir()) == [path]
