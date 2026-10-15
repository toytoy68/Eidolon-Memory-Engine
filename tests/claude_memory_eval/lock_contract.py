# ==========================================================
# Projet      : Eidolon Memory Engine
# Organisation: Eidolon Core Technologies (ECT)
# Fichier     : tests/claude_memory_eval/lock_contract.py
# Description : Prototype EXPÉRIMENTAL de verrou compatible avec un canon en lecture seule (Claude, G262-3)
# Standard    : Eidolon Presentation Standard v1
# ==========================================================
"""EXPERIMENTAL, test-only, Linux (flock). NOT wired to core/persistence.py.

One rule above all: readers and writers of one canon must lock the SAME inode. The location is therefore
resolved from the canon itself, never from a reader's own configuration:

- LEGACY (no manifest): the existing ``<canon>/.write.lock``. Writers keep core.persistence (open 'a+b',
  flock). A read-only reader opens the PRE-EXISTING file O_RDONLY and flocks it: flock needs no write
  access, and the lock is shared with writers through the inode, across a read-only bind mount.
- EXTERNAL (manifest ``<canon>/.lockspace.json`` written once at preparation): the lock lives in a state
  directory; the manifest records its path and (st_dev, st_ino, st_ctime_ns). Everyone verifies it.

After flock, the path must still name the locked inode; otherwise LOCK_SUBSTITUTED. A reader never
creates a lock (LOCK_ABSENT) and never proceeds unlocked. Proposal:
Core docs/proposals/2026-10-15-readonly-lock-contract.md.
"""
from contextlib import contextmanager
import fcntl
import json
import os
from pathlib import Path
import stat

MANIFEST = ".lockspace.json"
_after_open = None   # test hook: runs between open and flock


class LockRefused(OSError):
    def __init__(self, code):
        super().__init__(code)
        self.code = code


class LockBusy(LockRefused):
    pass


def _identity(st):
    return (st.st_dev, st.st_ino)


def _fingerprint(st):
    # An inode number is reused once a file is deleted: (dev, ino) alone cannot tell a replacement made
    # with unlink + create. ctime does not move when the lock is opened or flocked, only on metadata change.
    return (st.st_dev, st.st_ino, st.st_ctime_ns)


def resolve(canon_root):
    """('legacy', path, None) or ('external', path, (dev, ino)), from the canon only."""
    canon = Path(canon_root)
    manifest = canon / MANIFEST
    try:
        st = os.lstat(manifest)
    except FileNotFoundError:
        return "legacy", canon / ".write.lock", None
    if not stat.S_ISREG(st.st_mode) or st.st_size > 4096:
        raise LockRefused("LOCK_MANIFEST_INVALID")
    fd = os.open(manifest, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    with os.fdopen(fd, "rb") as handle:
        raw = handle.read(4097)
    try:
        value = json.loads(raw)
        path, mark = Path(value["path"]), (value["dev"], value["ino"], value["ctime_ns"])
        if (set(value) != {"schema", "path", "dev", "ino", "ctime_ns"} or value["schema"] != "eidolon-lockspace/1"
                or not path.is_absolute() or ".." in path.parts or any(type(x) is not int for x in mark)):
            raise ValueError
    except (ValueError, KeyError, TypeError):
        raise LockRefused("LOCK_MANIFEST_INVALID") from None
    return "external", path, mark


def prepare_external(canon_root, state_dir):
    """Preparation step, run once by the administrator BEFORE rights are reduced. Creates nothing twice."""
    canon, lock = Path(canon_root), Path(state_dir) / "canon.lock"
    if (canon / MANIFEST).exists():
        raise LockRefused("LOCK_ALREADY_PREPARED")
    fd = os.open(lock, os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
    st = os.fstat(fd)
    os.close(fd)
    body = json.dumps({"schema": "eidolon-lockspace/1", "path": str(lock), "dev": st.st_dev, "ino": st.st_ino,
                       "ctime_ns": st.st_ctime_ns})
    (canon / MANIFEST).write_text(body)
    return lock


@contextmanager
def locked(canon_root, *, blocking=True):
    """Exclusive lock for a READ-ONLY participant (the bridge). Never creates, never writes."""
    kind, path, expected = resolve(canon_root)
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    except FileNotFoundError:
        raise LockRefused("LOCK_ABSENT") from None
    except OSError as exc:
        if exc.errno == 40:   # ELOOP: the lock is a symlink
            raise LockRefused("LOCK_SYMLINK") from None
        raise
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode) or (expected is not None and _fingerprint(st) != expected):
            raise LockRefused("LOCK_SUBSTITUTED")
        if _after_open is not None:
            _after_open()
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | (0 if blocking else fcntl.LOCK_NB))
        except BlockingIOError:
            raise LockBusy("LOCK_BUSY") from None
        try:
            current = os.lstat(path)
        except FileNotFoundError:
            current = None
        if current is None or _identity(current) != _identity(st):
            fcntl.flock(fd, fcntl.LOCK_UN)
            raise LockRefused("LOCK_SUBSTITUTED")   # the path no longer names the inode we hold
        try:
            yield kind
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
    finally:
        os.close(fd)
