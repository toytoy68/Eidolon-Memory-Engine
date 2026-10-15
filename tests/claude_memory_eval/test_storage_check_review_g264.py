# ==========================================================
# Projet      : Eidolon Memory Engine
# Organisation: Eidolon Core Technologies (ECT)
# Fichier     : tests/claude_memory_eval/test_storage_check_review_g264.py
# Description : Contre-revue du diagnostic --check-storage G265 : confidentialité, effets, contention, reprise, CLI (G264-1 à 4)
# Standard    : Eidolon Presentation Standard v1
# ==========================================================
"""Synthetic storage, real subprocesses. Distinct from Codex's tests/test_storage_check_g265.py.

Every CLI run goes through an audit-hook wrapper: any socket, any write-intent open/mkdir/rename/remove
and any import of a model library under the run is recorded, so "no effect" is observed, not assumed."""
import json
import os
from pathlib import Path
import subprocess
import sys
import textwrap
import time

import pytest

from services import memory_bridge as bridge
from tests.test_contextual_recall import backend, store
from tests.test_migration_converter import fingerprints

pytestmark = pytest.mark.skipif(not sys.platform.startswith("linux"), reason="Linux readonly storage contract")
REPO = Path(__file__).resolve().parents[2]
SENTINELS = ("SECRETPATHab12", "secret-id-zz9", "SECRETCONTENTqq7", "SECRETTOKEN", "SECRETERRORxx1")
KEYS = {"schema", "scope", "state", "read_only_locks", "issues", "warnings"}

WRAPPER = textwrap.dedent("""
    import json, os, runpy, sys
    events = []
    def hook(event, args):
        if event == "socket.__new__" or event.startswith("socket.") and event != "socket.getaddrinfo":
            events.append(event)
        elif event == "open" and isinstance(args[0], (str, bytes, os.PathLike)):
            mode, flags = args[1], args[2]
            if (mode and any(c in mode for c in "wax+")) or flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT):
                events.append("write-open")
        elif event in ("os.mkdir", "os.rename", "os.replace", "os.remove", "os.rmdir", "os.chmod", "os.truncate"):
            events.append(event)
    sys.addaudithook(hook)
    sys.argv = ["memory_bridge"] + sys.argv[1:]
    code = 0
    try:
        runpy.run_module("services.memory_bridge", run_name="__main__")
    except SystemExit as exc:
        code = exc.code if isinstance(exc.code, int) else 1
    heavy = sorted(m for m in ("torch", "sentence_transformers", "transformers") if m in sys.modules)
    sys.stderr.write("\\n@@AUDIT@@" + json.dumps(dict(events=sorted(set(events)), heavy=heavy)))
    sys.exit(code)
""")


def cli(root, *args, token=None):
    env = {k: v for k, v in os.environ.items() if k != "EIDOLON_MEMORY_BRIDGE_TOKEN"}
    if token is not None:
        env["EIDOLON_MEMORY_BRIDGE_TOKEN"] = token
    r = subprocess.run([sys.executable, "-B", "-c", WRAPPER, "--root", str(root), "--check-storage", *args],
                       cwd=REPO, env=env, capture_output=True, text=True, timeout=30)
    err, _, audit = r.stderr.partition("\n@@AUDIT@@")
    return r.returncode, r.stdout, err, json.loads(audit) if audit else None


def corpus(tmp_path):
    root = tmp_path / "SECRETPATHab12"
    data = backend(root)
    store(data, "secret-id-zz9", content="SECRETCONTENTqq7 power measurement")
    (root / "memory/persistent/threads").mkdir()
    (root / "memory/persistent/threads/.write.lock").touch()
    return root


def report(code, out, err, audit, state):
    assert code == bridge.STORAGE_CHECK_EXIT[state], (code, out, err)
    value = json.loads(out)
    assert set(value) == KEYS and value["state"] == state and len(out.splitlines()) == 1
    for s in SENTINELS:
        assert s not in out and s not in err, s
    assert audit == {"events": [], "heavy": []}, audit       # no socket, no write, no model library
    return value


# --- G264-1: confidentiality and absence of effects -----------------------------------------------

@pytest.mark.parametrize("token", [None, "", "SECRETTOKEN", "SECRETTOKEN" * 500, "x" * 40])
def test_ready_whatever_the_token_with_no_effect_and_no_sentinel(tmp_path, token):
    root = corpus(tmp_path)
    before = fingerprints(root)
    report(*cli(root, token=token), "READY")
    assert fingerprints(root) == before


@pytest.mark.parametrize("state", ["BLOCKED", "UNAVAILABLE"])
def test_failure_states_never_echo_private_paths_ids_or_content(tmp_path, state):
    root = corpus(tmp_path)
    if state == "BLOCKED":
        (root / "memory/persistent/SECRETERRORxx1.md").write_text("SECRETCONTENTqq7 not front matter")
    else:
        (root / "memory/persistent/threads/.write.lock").unlink()
    before = fingerprints(root)
    report(*cli(root, token="SECRETTOKEN"), state)
    assert fingerprints(root) == before


# --- G264-2: startup contention -------------------------------------------------------------------

HOLDER = textwrap.dedent("""
    import pathlib, sys, time
    sys.path.insert(0, sys.argv[1])
    from core.persistence import exclusive_write
    root, gate = pathlib.Path(sys.argv[2]), pathlib.Path(sys.argv[3])
    with exclusive_write(root):
        print("held", flush=True)
        while not gate.exists():
            time.sleep(0.01)
""")


def hold(lock_root, gate):
    p = subprocess.Popen([sys.executable, "-c", HOLDER, str(REPO), str(lock_root), str(gate)],
                         stdout=subprocess.PIPE, text=True)
    assert p.stdout.readline().strip() == "held"
    return p


@pytest.mark.parametrize("held", ["memory/persistent", "memory/persistent/threads"])
def test_busy_at_once_while_a_writer_holds_either_lock_then_ready(tmp_path, held):
    root = corpus(tmp_path)
    inodes = {p: p.stat().st_ino for p in root.rglob(".write.lock")}
    gate = tmp_path / "release"
    writer = hold(root / held, gate)
    try:
        start = time.monotonic()
        report(*cli(root), "BUSY")
        assert time.monotonic() - start < 5                       # did not wait for the holder
    finally:
        gate.touch()
        writer.wait(5)
        writer.stdout.close()
    report(*cli(root), "READY")
    assert {p: p.stat().st_ino for p in root.rglob(".write.lock")} == inodes


def test_busy_on_threads_releases_persistent_at_once(tmp_path):
    """The check takes persistent THEN threads; failing on threads must not keep persistent."""
    root = corpus(tmp_path)
    gate = tmp_path / "release"
    writer = hold(root / "memory/persistent/threads", gate)
    try:
        report(*cli(root), "BUSY")
        probe = subprocess.run([sys.executable, "-c", textwrap.dedent(f"""
            import sys, pathlib
            sys.path.insert(0, {str(REPO)!r})
            from core.persistence import exclusive_write, RepositoryBusy
            try:
                with exclusive_write(pathlib.Path({str(root / 'memory/persistent')!r}), blocking=False):
                    print("free")
            except RepositoryBusy:
                print("STILL HELD")
        """)], capture_output=True, text=True, timeout=20)
        assert probe.stdout.strip() == "free"
    finally:
        gate.touch()
        writer.wait(5)
        writer.stdout.close()


# --- G264-3: recovery required vs derived state vs access error -----------------------------------

def test_incomplete_or_corrupt_journals_block_and_nothing_is_repaired(tmp_path):
    root = corpus(tmp_path)
    ops = root / "memory/history/operations/information-write-v1"
    ops.mkdir(parents=True, exist_ok=True)
    (ops / ("0" * 32 + ".json")).write_text('{"truncated": ')
    before = fingerprints(root)
    value = report(*cli(root), "BLOCKED")
    assert value["issues"] >= 1 and fingerprints(root) == before   # no repair, no quarantine


def test_derived_or_unrelated_directories_do_not_block_the_canon(tmp_path):
    root = corpus(tmp_path)
    for derived in ("index", "qdrant", "cache", "memory/index-state"):
        (root / derived).mkdir(parents=True)
        (root / derived / "stale.json").write_text("{not even json")
    report(*cli(root), "READY")


@pytest.mark.skipif(os.geteuid() == 0, reason="root reads any file; run under an ordinary UID")
def test_an_unreadable_canonical_file_is_not_ready(tmp_path):
    root = corpus(tmp_path)
    target = root / "memory/persistent/secret-id-zz9.md"
    target.chmod(0)
    try:
        code, out, err, audit = cli(root)
        assert json.loads(out)["state"] in ("BLOCKED", "UNAVAILABLE") and code != 0
    finally:
        target.chmod(0o600)


def test_the_unprivileged_cases_were_executed():
    if os.geteuid() != 0:
        return                                                   # already unprivileged: ran directly
    refused = _privilege_drop_refused()
    if refused:
        pytest.skip(refused)
    import shutil
    import tempfile
    base = Path(tempfile.mkdtemp(prefix="g264-nobody-"))         # /tmp, not the root-only pytest tmp
    copy = base / "repo"
    shutil.copytree(REPO, copy, ignore=shutil.ignore_patterns(".git", "__pycache__", ".pytest_cache"))
    for p in [base, copy, *copy.rglob("*")]:
        p.chmod(p.stat().st_mode | 0o005 | (0o002 if p in (base, copy) else 0))
    try:
        _run_unprivileged(copy)
    finally:
        shutil.rmtree(base, ignore_errors=True)


def _run_unprivileged(copy):
    r = subprocess.run(["setpriv", "--reuid=65534", "--regid=65534", "--clear-groups", sys.executable, "-m",
                        "pytest", "-q", "-p", "no:cacheprovider", "-k", "unreadable",
                        "tests/claude_memory_eval/test_storage_check_review_g264.py"],
                       cwd=copy, capture_output=True, text=True, timeout=180,
                       env=dict(os.environ, HOME=str(copy), PYTHONPATH=str(copy)))
    assert r.returncode == 0 and "1 passed" in r.stdout, r.stdout[-2000:] + r.stderr[-2000:]


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


# --- G264-4: CLI separation and exit codes --------------------------------------------------------

@pytest.mark.parametrize("args", [["--port", "18765"], ["--reranker-cache", "/nonexistent"]])
def test_server_options_are_refused_in_check_mode_without_effect(tmp_path, args):
    root = corpus(tmp_path)
    code, out, err, audit = cli(root, *args)
    assert code != 0 and out == "" and "usage" in err and audit == {"events": [], "heavy": []}


# G268: C189 finding fixed; keep Claude's assertion as an ordinary regression.
def test_a_usage_error_never_shares_an_exit_code_with_a_diagnostic_state(tmp_path):
    code, out, err, _ = cli(corpus(tmp_path), "--port", "18765")
    assert code not in bridge.STORAGE_CHECK_EXIT.values()


def test_check_mode_accepts_the_explicit_read_only_flag_and_serve_mode_keeps_its_token(tmp_path):
    root = corpus(tmp_path)
    report(*cli(root, "--read-only-storage"), "READY")
    env = {k: v for k, v in os.environ.items() if k != "EIDOLON_MEMORY_BRIDGE_TOKEN"}
    r = subprocess.run([sys.executable, "-B", "-m", "services.memory_bridge", "--root", str(root),
                        "--read-only-storage", "--port", "18999"], cwd=REPO, env=env, capture_output=True,
                       text=True, timeout=20)
    assert r.returncode == 2 and "EIDOLON_MEMORY_BRIDGE_TOKEN" in r.stderr   # never starts without a token


def test_unsupported_platform_is_explicit_not_a_fallback(tmp_path, monkeypatch):
    import core.persistence as persistence
    monkeypatch.setattr(persistence.sys, "platform", "win32")
    assert bridge.check_storage(corpus(tmp_path))["state"] == "UNSUPPORTED"


def test_a_writer_arriving_between_preflight_and_audit_gives_busy_not_a_hang(tmp_path, monkeypatch):
    """build_recall's preflight is non-blocking, but the audit's own lock must be too: a writer can take
    the lock in between. Killed nowhere else: with blocking=True the check waited for the writer."""
    import threading
    root = corpus(tmp_path)
    gate = tmp_path / "release"
    holders = []
    real = bridge.build_recall

    def build_then_writer_arrives(*args, **kwargs):
        recall = real(*args, **kwargs)                            # preflight passes: storage is free
        holders.append(hold(root / "memory/persistent", gate))    # then a writer takes the lock
        return recall
    monkeypatch.setattr(bridge, "build_recall", build_then_writer_arrives)
    result = {}
    worker = threading.Thread(target=lambda: result.update(bridge.check_storage(root)), daemon=True)
    worker.start()
    worker.join(5)
    try:
        assert not worker.is_alive(), "the diagnostic waited for the writer"
        assert result["state"] == "BUSY"
    finally:
        gate.touch()
        for p in holders:
            p.wait(5)
            p.stdout.close()
        worker.join(5)
