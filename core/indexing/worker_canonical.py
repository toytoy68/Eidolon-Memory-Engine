"""Canonical Markdown reader for isolated index-worker validation.

Requires a trusted, private persistent root. This is not a transaction lock:
production callers must coordinate with canonical writers before use.
"""
from hashlib import sha256
from contextlib import contextmanager
import os
from pathlib import Path
import re
import stat

from core.backend.filesystem import FilesystemBackend

@contextmanager
def _directory(path):
    """Walk every component relative to an open directory; never follow links."""
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
    fd = os.open(path.anchor, flags)
    try:
        for part in path.parts[1:]:
            if part == "..":
                raise ValueError("canonical root contains parent traversal")
            child = os.open(part, flags, dir_fd=fd)
            os.close(fd)
            fd = child
        yield fd
    finally:
        os.close(fd)


def _identity(info):
    return info.st_dev, info.st_ino


def _version(info):
    return (_identity(info), info.st_size, info.st_mtime_ns, info.st_ctime_ns)


class CanonicalReader:
    def __init__(self, persistent_root):
        root = Path(persistent_root).absolute()
        try:
            with _directory(root) as fd:
                self._root_identity = _identity(os.fstat(fd))
        except OSError as exc:
            raise ValueError("canonical root unavailable or unsafe") from exc
        self.root = root

    def __call__(self, information_id):
        if type(information_id) is not str or not re.fullmatch(r"[A-Za-z0-9._-]+", information_id):
            raise ValueError("invalid canonical identity")
        name = information_id + ".md"
        try:
            with _directory(self.root) as root_fd:
                if _identity(os.fstat(root_fd)) != self._root_identity:
                    raise ValueError("canonical root changed")
                fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC |
                             os.O_NONBLOCK, dir_fd=root_fd)
                with os.fdopen(fd, "rb") as handle:
                    before = os.fstat(handle.fileno())
                    if not stat.S_ISREG(before.st_mode):
                        raise ValueError("canonical file absent or unsafe")
                    raw = handle.read()
                    after = os.fstat(handle.fileno())
                current = os.stat(name, dir_fd=root_fd, follow_symlinks=False)
                if (_version(before) != _version(after)
                        or _version(after) != _version(current)):
                    raise ValueError("canonical file changed during read")
                with _directory(self.root) as checked_fd:
                    if _identity(os.fstat(checked_fd)) != self._root_identity:
                        raise ValueError("canonical root changed during read")
        except OSError as exc:
            raise ValueError("canonical file absent or unsafe") from exc
        memory = FilesystemBackend._deserialize(raw.decode("utf-8"))
        if memory.information_id != information_id or type(memory.revision) is not int or memory.revision < 1:
            raise ValueError("canonical identity or revision mismatch")
        return memory, sha256(raw).hexdigest()
