# ==========================================================
# Projet      : Eidolon Memory Engine
# Organisation: Eidolon Core Technologies (ECT)
# Fichier     : core/persistence.py
# Description : Cooperative cross-process locking for filesystem repositories.
# Standard    : Eidolon Presentation Standard v1
# ==========================================================

"""Cooperative cross-process locking for filesystem repositories.

All writers sharing a storage root must use this lock. Legacy CLI writers
must be stopped while the new repositories write to the same data.
"""
from contextlib import contextmanager
from functools import wraps
import errno
import os
import time
from pathlib import Path
from tempfile import NamedTemporaryFile
from threading import local


class RepositoryBusy(BlockingIOError):
    """The cooperative writer lock is held by another thread or process."""


_held_locks = local()


def has_symlink_component(path: Path) -> bool:
    """Inspect the path as written, without resolving away linked ancestors."""
    path = Path(path).absolute()
    return any(component.is_symlink() for component in (path, *path.parents))


@contextmanager
def _exclusive_write(root, *, blocking=True):
    # Keep the lock file: unlinking it could split waiters across two inodes.
    lock_path = root / ".write.lock"
    if lock_path.is_symlink():
        raise ValueError("writer lock file is a symlink")
    with lock_path.open("a+b") as handle:
        if os.name == "nt":
            import msvcrt
            # Windows permits byte-range locks beyond EOF; do not initialize
            # the byte before locking (another process may already hold it).
            deadline = time.monotonic() + 30
            while True:
                handle.seek(0)
                try:
                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                    break
                except OSError as exc:
                    if not blocking:
                        if exc.errno in {errno.EACCES, errno.EAGAIN, errno.EDEADLK}:
                            raise RepositoryBusy('repository writer is busy') from exc
                        raise
                    if time.monotonic() >= deadline:
                        raise TimeoutError("Timed out waiting for repository writer")
                    time.sleep(0.01)
            try:
                yield
            finally:
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | (0 if blocking else fcntl.LOCK_NB))
            except BlockingIOError as exc:
                raise RepositoryBusy('repository writer is busy') from exc
            try:
                yield
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


@contextmanager
def exclusive_write(root, *, blocking=True):
    """Reentrant within a thread; other threads/processes still acquire the OS lock."""
    if type(blocking) is not bool:
        raise ValueError('blocking must be boolean')
    root = Path(root)
    if has_symlink_component(root) or (root / ".write.lock").is_symlink():
        raise ValueError("writer lock path contains a symlink")
    key = str(root.resolve())
    held = getattr(_held_locks, "roots", None)
    if held is None:
        held = _held_locks.roots = set()
    if key in held:
        yield
        return
    lock = _exclusive_write(root) if blocking else _exclusive_write(root, blocking=False)
    with lock:
        held.add(key)
        try:
            yield
        finally:
            held.remove(key)


def write_lock_held(root):
    """Whether this thread currently owns the cooperative repository lock."""
    return str(Path(root).resolve()) in getattr(_held_locks, 'roots', set())


def durable_replace(source, destination):
    """Publish a flushed file, then persist its directory entry on POSIX."""
    from core.operations.read_phase import invalidate_publication
    invalidate_publication(destination)
    os.replace(source, destination)
    if os.name != "nt":
        descriptor = os.open(destination.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)


def atomic_write_text(path: Path, content: str) -> None:
    """Flush a UTF-8 file and publish it with an atomic, durable rename."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                prefix=f".{path.name}.", suffix=".tmp", delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        durable_replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def serialized_write(root_attribute):
    """Protect the complete read/check/write sequence, not just replacement."""
    def decorate(method):
        @wraps(method)
        def wrapped(self, *args, **kwargs):
            with exclusive_write(getattr(self, root_attribute)):
                return method(self, *args, **kwargs)
        return wrapped
    return decorate
