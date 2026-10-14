"""Canonical Markdown reader for isolated index-worker validation.

Requires a trusted, private persistent root. This is not a transaction lock:
production callers must coordinate with canonical writers before use.
"""
from hashlib import sha256
from pathlib import Path
import re

from core.backend.filesystem import FilesystemBackend
from core.persistence import has_symlink_component


class CanonicalReader:
    def __init__(self, persistent_root):
        root = Path(persistent_root)
        if not root.is_dir() or has_symlink_component(root):
            raise ValueError("canonical root unavailable or unsafe")
        self.root = root

    def __call__(self, information_id):
        if type(information_id) is not str or not re.fullmatch(r"[A-Za-z0-9._-]+", information_id):
            raise ValueError("invalid canonical identity")
        path = self.root / (information_id + ".md")
        if has_symlink_component(path) or not path.is_file():
            raise ValueError("canonical file absent or unsafe")
        raw = path.read_bytes()
        if has_symlink_component(path):
            raise ValueError("canonical path changed")
        memory = FilesystemBackend._deserialize(raw.decode("utf-8"))
        if memory.information_id != information_id or type(memory.revision) is not int or memory.revision < 1:
            raise ValueError("canonical identity or revision mismatch")
        return memory, sha256(raw).hexdigest()
