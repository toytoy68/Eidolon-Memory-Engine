# ==========================================================
# Projet      : Eidolon Memory Engine
# Organisation: Eidolon Core Technologies (ECT)
# Fichier     : tests/claude_memory_eval/test_lock_contract_g262.py
# Description : Verrou compatible lecture seule : exclusion interprocessus, absence, substitution, montage RO réel (G262-3)
# Standard    : Eidolon Presentation Standard v1
# ==========================================================
"""Synthetic directories. Writers are the REAL core.persistence.exclusive_write in another process.
The read-only bind-mount case runs only where `unshare -m` is permitted (skipped otherwise, never passed)."""
import os
from pathlib import Path
import shutil
import subprocess
import sys
import textwrap

import pytest

import tests.claude_memory_eval.lock_contract as lc

REPO = Path(__file__).resolve().parents[2]


def canon(tmp_path, lock=True):
    root = tmp_path / "memory/persistent"
    root.mkdir(parents=True)
    if lock:
        (root / ".write.lock").touch()
    return root


def hold_writer(root):
    """Start a process holding the REAL writer lock; returns (process, release_file)."""
    gate = root.parent / "release"
    code = textwrap.dedent(f"""
        import sys, time, pathlib
        sys.path.insert(0, {str(REPO)!r})
        from core.persistence import exclusive_write
        with exclusive_write(pathlib.Path({str(root)!r})):
            print("held", flush=True)
            while not pathlib.Path({str(gate)!r}).exists():
                time.sleep(0.01)
    """)
    proc = subprocess.Popen([sys.executable, "-c", code], stdout=subprocess.PIPE, text=True)
    assert proc.stdout.readline().strip() == "held"
    return proc, gate


def test_a_read_only_reader_and_the_real_writer_exclude_each_other(tmp_path):
    root = canon(tmp_path)
    proc, gate = hold_writer(root)
    try:
        with pytest.raises(lc.LockBusy):
            with lc.locked(root, blocking=False):
                pass
    finally:
        gate.touch()
        proc.wait(5)
        proc.stdout.close()
    with lc.locked(root, blocking=False) as kind:
        assert kind == "legacy"
        from core.persistence import RepositoryBusy, exclusive_write
        code = textwrap.dedent(f"""
            import sys, pathlib
            sys.path.insert(0, {str(REPO)!r})
            from core.persistence import RepositoryBusy, exclusive_write
            try:
                with exclusive_write(pathlib.Path({str(root)!r}), blocking=False):
                    print("WRITER ENTERED")
            except RepositoryBusy:
                print("writer busy")
        """)
        out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=20).stdout
        assert out.strip() == "writer busy"


def test_a_reader_never_creates_the_lock_nor_writes(tmp_path):
    root = canon(tmp_path, lock=False)
    with pytest.raises(lc.LockRefused) as caught:
        with lc.locked(root):
            pass
    assert caught.value.code == "LOCK_ABSENT" and not (root / ".write.lock").exists()


def test_a_symlinked_or_substituted_lock_is_refused(tmp_path, monkeypatch):
    root = canon(tmp_path)
    (root / ".write.lock").unlink()
    (root / ".write.lock").symlink_to(tmp_path / "elsewhere")
    with pytest.raises(lc.LockRefused, match="LOCK_SYMLINK"):
        with lc.locked(root):
            pass
    (root / ".write.lock").unlink()
    (root / ".write.lock").touch()

    def swap():                                    # another inode takes the name between open and flock
        os.replace(tmp_path / "other", root / ".write.lock")
    (tmp_path / "other").touch()
    monkeypatch.setattr(lc, "_after_open", swap)
    with pytest.raises(lc.LockRefused, match="LOCK_SUBSTITUTED"):
        with lc.locked(root):
            pass


def test_external_space_has_a_stable_identity_and_detects_substitution(tmp_path):
    root, state = canon(tmp_path, lock=False), tmp_path / "state"
    state.mkdir(mode=0o700)
    lock = lc.prepare_external(root, state)
    with pytest.raises(lc.LockRefused, match="LOCK_ALREADY_PREPARED"):
        lc.prepare_external(root, state)                  # never a second lock space
    inode = lock.stat().st_ino
    for _ in range(2):                                    # "restart": a fresh open finds the same inode
        with lc.locked(root) as kind:
            assert kind == "external" and lock.stat().st_ino == inode
    lock.unlink()
    lock.touch()                    # same path, new file (often the SAME recycled inode number): refused
    with pytest.raises(lc.LockRefused, match="LOCK_SUBSTITUTED"):
        with lc.locked(root):
            pass


def test_two_processes_in_the_external_space_exclude_each_other(tmp_path):
    root, state = canon(tmp_path, lock=False), tmp_path / "state"
    state.mkdir()
    lc.prepare_external(root, state)
    with lc.locked(root):
        code = textwrap.dedent(f"""
            import sys, pathlib
            sys.path.insert(0, {str(REPO)!r})
            import tests.claude_memory_eval.lock_contract as lc
            try:
                with lc.locked(pathlib.Path({str(root)!r}), blocking=False):
                    print("ENTERED")
            except lc.LockBusy:
                print("busy")
        """)
        out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=20, cwd=REPO)
        assert out.stdout.strip() == "busy", out.stderr


@pytest.mark.parametrize("body", ['{"schema": "x"}', "not json", '{"schema": "eidolon-lockspace/1", "path": "rel",'
                                  ' "dev": 1, "ino": 2, "ctime_ns": 3}'])
def test_an_invalid_manifest_is_refused(tmp_path, body):
    root = canon(tmp_path)
    (root / lc.MANIFEST).write_text(body)
    with pytest.raises(lc.LockRefused, match="LOCK_MANIFEST_INVALID"):
        with lc.locked(root):
            pass


UNSHARE = shutil.which("unshare") and subprocess.run(
    ["unshare", "-m", "true"], capture_output=True).returncode == 0


@pytest.mark.skipif(not UNSHARE, reason="mount namespaces not permitted here")
def test_on_a_real_read_only_bind_mount_the_legacy_lock_works_for_readers_and_a_plus_b_does_not(tmp_path):
    root = canon(tmp_path)
    ro = tmp_path / "ro"
    ro.mkdir()
    proc, gate = hold_writer(root)                        # the writer uses the read-write path
    script = textwrap.dedent(f"""
        import errno, sys, pathlib
        sys.path.insert(0, {str(REPO)!r})
        import tests.claude_memory_eval.lock_contract as lc
        ro = pathlib.Path({str(ro)!r})
        try:
            open(ro / ".write.lock", "a+b")
            print("a+b OPENED")
        except OSError as e:
            print("a+b", errno.errorcode[e.errno])
        try:
            with lc.locked(ro, blocking=False):
                print("ENTERED WHILE WRITER HOLDS")
        except lc.LockBusy:
            print("busy")
        pathlib.Path({str(gate)!r}).touch()
        import time; time.sleep(0.3)
        with lc.locked(ro):
            print("entered after writer")
    """)
    try:
        out = subprocess.run(["unshare", "-m", "sh", "-c",
                              f"mount --bind {root} {ro} && mount -o remount,ro,bind {ro} && "
                              f"{sys.executable} -c \"$0\"", script],
                             capture_output=True, text=True, timeout=30, cwd=REPO)
    finally:
        gate.touch()
        proc.wait(5)
        proc.stdout.close()
    assert out.stdout.split("\n")[:3] == ["a+b EROFS", "busy", "entered after writer"], out.stdout + out.stderr
