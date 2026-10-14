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
    def __init__(self, persistent_root, *, max_bytes=None):
        if max_bytes is not None and (type(max_bytes) is not int or max_bytes < 1):
            raise ValueError("invalid canonical byte limit")
        self.max_bytes = max_bytes
        root = Path(persistent_root).absolute()
        try:
            with _directory(root) as fd:
                self._root_identity = _identity(os.fstat(fd))
        except OSError as exc:
            raise ValueError("canonical root unavailable or unsafe") from exc
        self.root = root

    def __call__(self, information_id):
        return self._read(information_id)

    def proven_absent(self, information_id):
        """Observe a missing leaf, never infer absence from an unreadable source.

        Caller holds the cooperative writer lock. Any directory entry (including
        a dangling link) means not absent. Errors and replaced roots fail closed.
        This observation is not a reusable deletion permission.
        """
        if type(information_id) is not str or not re.fullmatch(r"[A-Za-z0-9._-]+", information_id):
            raise ValueError("invalid canonical identity")
        try:
            with _directory(self.root) as fd:
                if _identity(os.fstat(fd)) != self._root_identity:
                    raise ValueError("canonical root changed")
                def missing():
                    try:
                        os.stat(information_id + ".md", dir_fd=fd, follow_symlinks=False)
                    except FileNotFoundError:
                        return True
                    return False
                absent = missing()
                with _directory(self.root) as checked_fd:
                    if _identity(os.fstat(checked_fd)) != self._root_identity:
                        raise ValueError("canonical root changed during absence check")
                absent = absent and missing()
                with _directory(self.root) as checked_fd:
                    if _identity(os.fstat(checked_fd)) != self._root_identity:
                        raise ValueError("canonical root changed during absence check")
                return absent
        except OSError as exc:
            raise ValueError("canonical absence unknown; root or leaf unavailable") from exc

    def information_ids(self, *, max_entries):
        """Bounded directory inventory through the pinned descriptor; no absence proof.

        Caller holds the canonical lock. Non-Markdown entries count toward the
        budget too; an oversized directory never produces a truncated inventory.
        """
        if type(max_entries) is not int or max_entries < 1:
            raise ValueError("invalid directory entry limit")
        with _directory(self.root) as fd:
            if _identity(os.fstat(fd)) != self._root_identity:
                raise ValueError("canonical root changed")
            names = []
            with os.scandir(fd) as entries:
                for count, entry in enumerate(entries, 1):
                    if count > max_entries:
                        raise ValueError("canonical inventory exceeds entry limit")
                    if entry.name.endswith(".md"):
                        names.append(entry.name[:-3])
            with _directory(self.root) as checked_fd:
                if _identity(os.fstat(checked_fd)) != self._root_identity:
                    raise ValueError("canonical root changed during inventory")
            return tuple(sorted(names))

    def read_sized(self, information_id):
        """Verified source and consumed bytes, for a complete snapshot budget."""
        return self._read(information_id, include_size=True)

    def read_durable(self, information_id):
        """Revalidate and flush canonical bytes/directory for INTENT recovery.

        Caller must hold the cooperative writer lock. Read-back alone does not
        prove that a writer flushed its rename before an interruption.
        """
        return self._read(information_id, durable=True)

    def _read(self, information_id, *, durable=False, include_size=False):
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
                    if self.max_bytes is not None and before.st_size > self.max_bytes:
                        raise ValueError("canonical file exceeds byte limit")
                    raw = handle.read() if self.max_bytes is None else handle.read(self.max_bytes + 1)
                    if self.max_bytes is not None and len(raw) > self.max_bytes:
                        raise ValueError("canonical file exceeds byte limit")
                    if durable:
                        os.fsync(handle.fileno())
                    after = os.fstat(handle.fileno())
                if durable:
                    os.fsync(root_fd)
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
        result = memory, sha256(raw).hexdigest()
        return (*result, len(raw)) if include_size else result
