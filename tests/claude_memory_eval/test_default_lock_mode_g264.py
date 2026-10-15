# ==========================================================
# Projet      : Eidolon Memory Engine
# Organisation: Eidolon Core Technologies (ECT)
# Fichier     : tests/claude_memory_eval/test_default_lock_mode_g264.py
# Description : G263 ne change pas le mode de verrou par défaut des écrivains, Linux et Windows simulé (Claude, G264-6)
# Standard    : Eidolon Presentation Standard v1
# ==========================================================
"""Synthetic directories. The Windows cases are a SIMULATION (os.name patched, fake msvcrt): they check the
code path chosen, not real Windows locking. The Linux read-only contract itself is not re-reviewed (G262-3)."""
import ast
import os
from pathlib import Path
import sys

import pytest

from core import persistence
from core.backend.filesystem import FilesystemBackend
from core.retrieval.contextual import ContextualRecall
from tests.test_contextual_recall import store

REPO = Path(__file__).resolve().parents[2]


def test_only_the_reader_can_ask_for_read_only_locks():
    """AST inventory: no writer in core/ or services/ passes read_only, and only ContextualRecall forwards it."""
    offenders = []
    for path in [*(REPO / "core").rglob("*.py"), *(REPO / "services").rglob("*.py")]:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and getattr(node.func, "id", getattr(node.func, "attr", None)) in (
                    "exclusive_write", "_exclusive_write"):
                names = {k.arg for k in node.keywords}
                star = any(k.arg is None for k in node.keywords)
                rel = path.relative_to(REPO).as_posix()
                if ("read_only" in names or star) and rel not in ("core/persistence.py",
                                                                    "core/retrieval/contextual.py"):
                    offenders.append(f"{rel}:{node.lineno}")
    assert offenders == []


def test_default_writer_lock_still_provisions_and_opens_for_writing(tmp_path, monkeypatch):
    modes = []
    real_open = Path.open

    def spy(self, mode="r", *a, **k):
        if self.name == ".write.lock":
            modes.append(mode)
        return real_open(self, mode, *a, **k)
    monkeypatch.setattr(Path, "open", spy)
    with persistence.exclusive_write(tmp_path):                 # absent lock: created, as before G263
        assert (tmp_path / ".write.lock").is_file()
    with persistence.exclusive_write(tmp_path, blocking=False):
        pass
    assert modes == ["a+b", "a+b"]


def test_default_backend_and_recall_keep_their_historic_behaviour(tmp_path):
    data = FilesystemBackend(tmp_path / "memory/persistent", tmp_path / "memory/history")
    assert (tmp_path / "memory/history/pending-delete").is_dir()     # still provisioned by default
    store(data, "a-power", content="power measurement")
    for lock in tmp_path.rglob(".write.lock"):
        lock.unlink()
    recall = ContextualRecall(data)
    assert recall.read_only_locks is False
    recall.recall("power")
    assert (tmp_path / "memory/persistent/.write.lock").is_file()   # created on demand, as before


def test_a_writer_may_nest_a_read_only_request_without_being_downgraded(tmp_path):
    (tmp_path / ".write.lock").touch()
    with persistence.exclusive_write(tmp_path):
        with persistence.exclusive_write(tmp_path, read_only=True):
            pass
        with persistence.exclusive_write(tmp_path):              # still a writer after the nested reader
            pass
    assert persistence.write_lock_held(tmp_path) is False


SIMULATION = """
import json, os, sys, types, pathlib
sys.path.insert(0, sys.argv[1])
root, case = pathlib.Path(sys.argv[2]), sys.argv[3]
calls, opened = [], []
fake = types.ModuleType("msvcrt")
fake.LK_NBLCK, fake.LK_UNLCK = 2, 0
fake.locking = lambda fd, mode, n: calls.append([mode, n])
sys.modules["msvcrt"] = fake
from core import persistence
class NtView:                       # SIMULATION: persistence alone sees os.name == "nt"; pathlib is untouched
    name = "nt"
    def __getattr__(self, attr):
        return getattr(os, attr)
persistence.os = NtView()
outcome = "ok"
if case == "writer":
    with persistence.exclusive_write(root):
        pass
else:
    sys.platform = "win32"
    real = os.open
    NtView.open = staticmethod(lambda *a, **k: opened.append(1) or real(*a, **k))
    try:
        with persistence.exclusive_write(root, read_only=True):
            outcome = "ACQUIRED"
    except NotImplementedError:
        outcome = "refused"
    try:
        from core.backend.filesystem import FilesystemBackend
        from core.retrieval.contextual import ContextualRecall
        ContextualRecall(FilesystemBackend(root / "p", root / "h"), read_only_locks=True)
        outcome += "+RECALL ACCEPTED"
    except NotImplementedError:
        outcome += "+recall refused"
print(json.dumps(dict(outcome=outcome, calls=calls, opened=len(opened))))
"""


def simulate(tmp_path, case):
    import json
    import subprocess
    r = subprocess.run([sys.executable, "-c", SIMULATION, str(REPO), str(tmp_path), case], capture_output=True,
                       text=True, timeout=30)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


def test_simulated_windows_default_writer_path_is_unchanged(tmp_path):
    result = simulate(tmp_path, "writer")
    assert result["calls"] == [[2, 1], [0, 1]] and (tmp_path / ".write.lock").is_file()


def test_simulated_windows_refuses_read_only_before_opening_anything(tmp_path):
    (tmp_path / ".write.lock").touch()
    result = simulate(tmp_path, "reader")
    assert result == {"outcome": "refused+recall refused", "calls": [], "opened": 0}
