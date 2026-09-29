"""Cooperative cross-process locking for filesystem repositories.

All writers sharing a storage root must use this lock. Legacy CLI writers
must be stopped while the new repositories write to the same data.
"""
from contextlib import contextmanager
from functools import wraps
import os
import time
from pathlib import Path
from tempfile import NamedTemporaryFile
from threading import local

_held_locks = local()


@contextmanager
def _exclusive_write(root):
    # Keep the lock file: unlinking it could split waiters across two inodes.
    with (root / ".write.lock").open("a+b") as handle:
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
                except OSError:
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
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


@contextmanager
def exclusive_write(root):
    """Reentrant within a thread; other threads/processes still acquire the OS lock."""
    key = str(root.resolve())
    held = getattr(_held_locks, "roots", None)
    if held is None:
        held = _held_locks.roots = set()
    if key in held:
        yield
        return
    with _exclusive_write(root):
        held.add(key)
        try:
            yield
        finally:
            held.remove(key)


def durable_replace(source, destination):
    """Publish a flushed file, then persist its directory entry on POSIX."""
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
