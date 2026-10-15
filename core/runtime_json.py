# ==========================================================
# Projet      : Eidolon Memory Engine
# Organisation: Eidolon Core Technologies (ECT)
# Fichier     : runtime_json.py
# Description : Lecture bornée d'un instantané JSON d'observation hôte (Claude, G256-7)
# Standard    : Eidolon Presentation Standard v1
# ==========================================================
"""Adopted from Claude G256/G258 by Codex G269. Reads one JSON object the host wrote, or refuses; never guesses, never waits.

- every path component is opened without following links, from the filesystem root;
- the leaf must be a regular file, single link, not group- or world-writable, opened non-blocking
  (a FIFO cannot hang the caller);
- size is bounded before and during the read; the file must not change or be replaced while read;
- strict UTF-8 without BOM, duplicate keys and NaN/Infinity refused, bounded nesting, object at the top.
Used for operator-owned runtime configuration and observations. Ancestor permissions remain the operator responsibility.
"""
import json
import math
import os
import re
import stat

MAX_SNAPSHOT_BYTES = 1024 * 1024   # hard ceiling of this reader; the caller chooses a lower budget
MAX_INTEGER_DIGITS = 18             # a host measure never needs more; far below int parsing limits
_NAME = re.compile(r"[A-Za-z0-9_-][A-Za-z0-9._-]{0,127}\.json\Z")
_after_read = None                 # test hook: runs between the read and the final identity check


class SnapshotRefused(ValueError):
    def __init__(self, code):
        super().__init__(code)
        self.code = code


def missing_primitives():
    """G258-7: the POSIX features this reader relies on. Any absence is an explicit refusal, never a fallback.

    Linux server: all present. Windows PC: no O_NOFOLLOW/O_DIRECTORY/O_NONBLOCK and no dir_fd support,
    so this reader refuses there; host observations are meant to be produced on the Linux server."""
    missing = [flag for flag in ("O_NOFOLLOW", "O_DIRECTORY", "O_NONBLOCK", "O_CLOEXEC")
               if not hasattr(os, flag)]
    if os.open not in os.supports_dir_fd:
        missing.append("dir_fd:open")
    if os.stat not in os.supports_dir_fd:
        missing.append("dir_fd:stat")
    if os.stat not in os.supports_follow_symlinks:
        missing.append("follow_symlinks:stat")
    return tuple(missing)


def _version(st):
    return (st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns, st.st_ctime_ns)


def _identity(st):
    return (st.st_dev, st.st_ino)


def _open_directory(path):
    if type(path) is not str or not os.path.isabs(path) or "\0" in path:
        raise SnapshotRefused("SNAPSHOT_PATH")
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
    fd = os.open("/", flags)
    try:
        for part in [p for p in path.split("/") if p]:
            if part in (".", ".."):
                raise SnapshotRefused("SNAPSHOT_PATH")
            try:
                child = os.open(part, flags, dir_fd=fd)
            except OSError:
                raise SnapshotRefused("SNAPSHOT_PATH") from None   # missing, not a directory, or a link
            os.close(fd)
            fd = child
        return fd
    except BaseException:
        os.close(fd)
        raise


def _unique(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise SnapshotRefused("SNAPSHOT_DUPLICATE_KEY")
        value[key] = item
    return value


def _constant(name):
    raise SnapshotRefused("SNAPSHOT_INVALID_JSON")


def _float(text):
    value = float(text)
    if not math.isfinite(value):          # 1e999 overflows to infinity without calling parse_constant
        raise SnapshotRefused("SNAPSHOT_INVALID_JSON")
    return value


def _int(text):
    if len(text.lstrip("-")) > MAX_INTEGER_DIGITS:
        raise SnapshotRefused("SNAPSHOT_INVALID_JSON")
    return int(text)


def _encodable(text):
    try:
        text.encode("utf-8")              # "\\ud800" escapes decode to lone surrogates
    except UnicodeEncodeError:
        raise SnapshotRefused("SNAPSHOT_ENCODING") from None


def _depth(value, limit):
    stack = [(value, 1)]
    while stack:
        item, depth = stack.pop()
        if isinstance(item, str):
            _encodable(item)
        if isinstance(item, dict):
            for key in item:
                _encodable(key)
        if isinstance(item, (dict, list)):
            if depth > limit:
                raise SnapshotRefused("SNAPSHOT_TOO_DEEP")
            stack.extend((child, depth + 1) for child in (item.values() if isinstance(item, dict) else item))


def read_json_snapshot(directory, name, *, max_bytes, max_depth=4):
    if type(name) is not str or _NAME.fullmatch(name) is None:
        raise SnapshotRefused("SNAPSHOT_PATH")
    if type(max_bytes) is not int or not 1 <= max_bytes <= MAX_SNAPSHOT_BYTES:
        raise SnapshotRefused("SNAPSHOT_BUDGET")
    if type(max_depth) is not int or not 1 <= max_depth <= 16:
        raise SnapshotRefused("SNAPSHOT_BUDGET")
    if missing_primitives():
        raise SnapshotRefused("SNAPSHOT_PLATFORM_UNSUPPORTED")
    dir_fd = _open_directory(directory)
    try:
        try:
            fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC, dir_fd=dir_fd)
        except OSError:
            raise SnapshotRefused("SNAPSHOT_UNAVAILABLE") from None    # absent, link, or unreadable
        try:
            before = os.fstat(fd)
            if stat.S_ISREG(before.st_mode) and before.st_nlink == 0:
                raise SnapshotRefused("SNAPSHOT_CHANGED")                  # replaced since our open
            if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
                raise SnapshotRefused("SNAPSHOT_NOT_REGULAR")
            if before.st_mode & (stat.S_IWGRP | stat.S_IWOTH):
                raise SnapshotRefused("SNAPSHOT_WRITABLE_BY_OTHERS")
            if before.st_size > max_bytes:
                raise SnapshotRefused("SNAPSHOT_TOO_LARGE")
            chunks, total = [], 0
            while total <= max_bytes:
                part = os.read(fd, max_bytes + 1 - total)
                if not part:
                    break
                chunks.append(part)
                total += len(part)
            data = b"".join(chunks)
            if len(data) > max_bytes:
                raise SnapshotRefused("SNAPSHOT_TOO_LARGE")
            if _after_read is not None:
                _after_read()
            after = os.fstat(fd)
            try:
                current = os.stat(name, dir_fd=dir_fd, follow_symlinks=False)
            except OSError:
                raise SnapshotRefused("SNAPSHOT_CHANGED") from None
            if not (_version(before) == _version(after) == _version(current)) or len(data) != before.st_size:
                raise SnapshotRefused("SNAPSHOT_CHANGED")
            # G258-6: the file is the same, but does the PATH still name this directory? An ancestor renamed,
            # replaced or turned into a link means the bytes no longer come from the path the host trusts.
            try:
                again = _open_directory(directory)
            except SnapshotRefused:
                raise SnapshotRefused("SNAPSHOT_PATH_CHANGED") from None
            try:
                if _identity(os.fstat(again)) != _identity(os.fstat(dir_fd)):
                    raise SnapshotRefused("SNAPSHOT_PATH_CHANGED")
            finally:
                os.close(again)
        finally:
            os.close(fd)
    finally:
        os.close(dir_fd)
    if data.startswith(b"\xef\xbb\xbf"):
        raise SnapshotRefused("SNAPSHOT_ENCODING")
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        raise SnapshotRefused("SNAPSHOT_ENCODING") from None
    try:
        value = json.loads(text, object_pairs_hook=_unique, parse_constant=_constant,
                           parse_float=_float, parse_int=_int)
    except RecursionError:
        raise SnapshotRefused("SNAPSHOT_TOO_DEEP") from None
    except SnapshotRefused:
        raise
    except ValueError:                     # JSONDecodeError and any number conversion error
        raise SnapshotRefused("SNAPSHOT_INVALID_JSON") from None
    if not isinstance(value, dict):
        raise SnapshotRefused("SNAPSHOT_INVALID_JSON")
    _depth(value, max_depth)
    return value
