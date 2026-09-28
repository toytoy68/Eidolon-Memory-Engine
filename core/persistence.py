"""Cooperative cross-process locking for filesystem repositories.

All writers sharing a storage root must use this lock. Legacy CLI writers
must be stopped while the new repositories write to the same data.
"""
from contextlib import contextmanager
from functools import wraps
import os
import time


@contextmanager
def exclusive_write(root):
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


def serialized_write(root_attribute):
    """Protect the complete read/check/write sequence, not just replacement."""
    def decorate(method):
        @wraps(method)
        def wrapped(self, *args, **kwargs):
            with exclusive_write(getattr(self, root_attribute)):
                return method(self, *args, **kwargs)
        return wrapped
    return decorate
