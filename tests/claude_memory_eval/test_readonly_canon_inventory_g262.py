# ==========================================================
# Projet      : Eidolon Memory Engine
# Organisation: Eidolon Core Technologies (ECT)
# Fichier     : tests/claude_memory_eval/test_readonly_canon_inventory_g262.py
# Description : Inventaire des écritures d'un rappel sur canon en lecture seule (Claude, G262-2)
# Standard    : Eidolon Presentation Standard v1
# ==========================================================
"""Synthetic canon only. Three independent views of the same question, "what does a recall write?":

1. a TRACE of every write-intent filesystem call under the bridge --root (calls still performed);
2. a simulated read-only mount: those calls raise EROFS (no real mount, no systemd);
3. real permissions: the canon is chmod-ed read-only and the recall runs under an ordinary UID
   (skipped under root, which ignores mode bits; run this file with an unprivileged UID to execute it).

The tests assert TODAY's contract, blocker included: the lock is opened 'a+b' even when it exists. They
are a regression inventory, not a fix; nothing removes or pre-creates the lock to make them pass.
"""
from contextlib import contextmanager
import builtins
import errno
import io
import os
from pathlib import Path
import stat
import subprocess
import sys

import pytest

from core.backend.filesystem import FilesystemBackend
from core.retrieval.contextual import ContextualRecall
from tests.test_contextual_recall import store

WRITE_FLAGS = os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND


def bridge_root(tmp_path, *, threads=False, lock=True):
    root = tmp_path / "bridge"
    data = FilesystemBackend(root / "memory/persistent", root / "memory/history")
    store(data, "a-power", content="power measurement")
    if threads:
        (root / "memory/persistent/threads").mkdir()
    if not lock:
        for p in root.rglob(".write.lock"):
            p.unlink()
    return root


@contextmanager
def writes_under(root, *, fail=False):
    """Record (operation, path relative to root, mode); with fail=True raise EROFS instead of writing."""
    root = Path(root).resolve()
    seen = []
    real = dict(open=builtins.open, os_open=os.open, mkdir=os.mkdir, replace=os.replace, rename=os.rename,
                unlink=os.unlink, rmdir=os.rmdir)

    def note(op, path, mode=""):
        try:
            rel = Path(os.path.abspath(path)).resolve().relative_to(root)
        except (ValueError, TypeError, OSError):
            return
        seen.append((op, str(rel), mode))
        if fail:
            raise OSError(errno.EROFS, os.strerror(errno.EROFS), str(path))

    def f_open(file, mode="r", *a, **k):
        if isinstance(file, (str, bytes, os.PathLike)) and any(c in mode for c in "wax+"):
            note("open", file, mode)
        return real["open"](file, mode, *a, **k)

    def f_os_open(path, flags, *a, **k):
        if flags & WRITE_FLAGS and k.get("dir_fd") is None:
            note("os.open", path, oct(flags & WRITE_FLAGS))
        return real["os_open"](path, flags, *a, **k)

    def wrap(name):
        def inner(path, *a, **k):
            if k.get("dir_fd") is None:
                note(name, path)
            return real[name](path, *a, **k)
        return inner

    patches = [(builtins, "open", f_open), (io, "open", f_open), (os, "open", f_os_open), (os, "mkdir", wrap("mkdir")),
               (os, "replace", wrap("replace")), (os, "rename", wrap("rename")), (os, "unlink", wrap("unlink")),
               (os, "rmdir", wrap("rmdir"))]
    saved = [(mod, name, getattr(mod, name)) for mod, name, _ in patches]
    for mod, name, fn in patches:
        setattr(mod, name, fn)
    try:
        yield seen
    finally:
        for mod, name, fn in saved:
            setattr(mod, name, fn)


def recall_once(root):
    data = FilesystemBackend(root / "memory/persistent", root / "memory/history")
    return ContextualRecall(data).recall("power")


# --- 1. trace ---------------------------------------------------------------------------------------

@pytest.mark.parametrize("threads", [False, True])
@pytest.mark.parametrize("lock", [True, False])
def test_the_write_inventory_of_one_recall(tmp_path, threads, lock):
    root = bridge_root(tmp_path, threads=threads, lock=lock)
    with writes_under(root) as seen:
        assert recall_once(root).items                        # the recall itself succeeds
    expected = [("mkdir", "memory/persistent", ""), ("mkdir", "memory/history/pending-delete", ""),
                ("open", "memory/persistent/.write.lock", "a+b")]
    if threads:
        expected.append(("open", "memory/persistent/threads/.write.lock", "a+b"))
    assert [s for s in seen if s[0] != "mkdir" or s[1] in ("memory/persistent", "memory/history/pending-delete")
            ] == expected, seen
    # mkdir is attempted with exist_ok=True: the directories already exist, nothing is created.
    assert all(op != "mkdir" or (root / rel).is_dir() for op, rel, _ in seen)


def test_a_recall_only_creates_missing_lock_files_and_changes_no_byte(tmp_path):
    root = bridge_root(tmp_path, threads=True, lock=False)
    before = {p: p.stat().st_mtime_ns for p in root.rglob("*") if p.is_file()}
    recall_once(root)
    after = {p: p.stat().st_mtime_ns for p in root.rglob("*") if p.is_file()}
    created = set(after) - set(before)
    assert {p.relative_to(root).as_posix() for p in created} == {
        "memory/persistent/.write.lock", "memory/persistent/threads/.write.lock"}
    assert all(p.stat().st_size == 0 for p in created)        # empty lock files, kept on purpose
    assert {p: after[p] for p in before} == before            # every existing file untouched


# --- 2. simulated read-only mount (EROFS) ----------------------------------------------------------

@pytest.mark.parametrize("lock", [True, False])
def test_a_read_only_mount_blocks_the_recall_on_the_lock_even_if_it_exists(tmp_path, lock):
    root = bridge_root(tmp_path, lock=lock)
    data = FilesystemBackend(root / "memory/persistent", root / "memory/history")
    recall = ContextualRecall(data)                           # constructors before the mount: fine
    with writes_under(root, fail=True) as seen:
        with pytest.raises(OSError) as caught:
            recall.recall("power")
    assert caught.value.errno == errno.EROFS
    assert seen == [("open", "memory/persistent/.write.lock", "a+b")]


def test_constructors_tolerate_a_read_only_mount_only_if_the_layout_already_exists(tmp_path):
    root = bridge_root(tmp_path)
    with writes_under(root, fail=True) as seen:
        ContextualRecall(FilesystemBackend(root / "memory/persistent", root / "memory/history"))
    assert [op for op, _, _ in seen] == ["mkdir", "mkdir"]   # attempted, refused, then accepted: exist_ok
    (root / "memory/history/pending-delete").rmdir()
    with writes_under(root, fail=True):
        with pytest.raises(OSError) as caught:
            FilesystemBackend(root / "memory/persistent", root / "memory/history")
    assert caught.value.errno == errno.EROFS                  # pending-delete must be prepared beforehand


# --- 3. real permissions under an ordinary UID ------------------------------------------------------

UNPRIVILEGED = os.geteuid() != 0


@pytest.mark.skipif(not UNPRIVILEGED, reason="root ignores mode bits; run under an ordinary UID")
@pytest.mark.parametrize("lock", [True, False])
def test_a_read_only_canon_by_permissions_blocks_the_recall(tmp_path, lock):
    root = bridge_root(tmp_path, lock=lock)
    targets = sorted((p for p in (root / "memory").rglob("*")), key=lambda p: -len(p.parts)) + [root / "memory"]
    try:
        for p in targets:
            p.chmod(0o555 if p.is_dir() else 0o444)
        data = FilesystemBackend(root / "memory/persistent", root / "memory/history")   # mkdir: EEXIST only
        with pytest.raises(PermissionError) as caught:
            ContextualRecall(data).recall("power")
        assert caught.value.filename.endswith(".write.lock")
    finally:
        for p in reversed(targets):
            p.chmod(0o700 if p.is_dir() else 0o600)


def test_the_permission_case_was_executed_somewhere():
    """Under root this file re-runs its permission tests under nobody, so they are never silently skipped."""
    if UNPRIVILEGED:
        return
    refused = _privilege_drop_refused()
    if refused:
        pytest.skip(refused)
    import shutil
    import tempfile
    copy = Path(tempfile.mkdtemp(prefix="g262-ro-"))
    here = Path(__file__).resolve().parents[2]
    shutil.copytree(here, copy, dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns(".git", "__pycache__", ".pytest_cache", ".venv", "node_modules"))
    for p in [copy, *copy.rglob("*")]:
        p.chmod(p.stat().st_mode | stat.S_IROTH | (stat.S_IXOTH if p.is_dir() else 0))
    copy.chmod(0o777)
    try:
        r = subprocess.run(["setpriv", "--reuid=65534", "--regid=65534", "--clear-groups", sys.executable, "-m",
                            "pytest", "-q", "-p", "no:cacheprovider", "-k", "permissions",
                            "tests/claude_memory_eval/test_readonly_canon_inventory_g262.py"],
                           cwd=copy, capture_output=True, text=True, timeout=120,
                           env=dict(os.environ, HOME=str(copy), PYTHONPATH=str(copy)))
        assert r.returncode == 0 and "2 passed" in r.stdout, r.stdout + r.stderr
    finally:
        shutil.rmtree(copy, ignore_errors=True)


def _privilege_drop_refused():
    """None when `setpriv` can really switch to nobody here; otherwise the reason (e.g. a root runtime
    without CAP_SETUID returns `setresuid: Invalid argument`). The caller SKIPS with it, never passes."""
    import shutil
    if not shutil.which("setpriv"):
        return "no setpriv to drop privileges"
    probe = subprocess.run(["setpriv", "--reuid=65534", "--regid=65534", "--clear-groups", "id", "-u"],
                           capture_output=True, text=True, timeout=30)
    if probe.returncode != 0 or probe.stdout.strip() != "65534":
        return f"this runtime cannot drop privileges: {(probe.stderr or probe.stdout).strip()[:200]}"
    return None
