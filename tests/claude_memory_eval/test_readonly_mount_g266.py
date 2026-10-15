# ==========================================================
# Projet      : Eidolon Memory Engine
# Organisation: Eidolon Core Technologies (ECT)
# Fichier     : tests/claude_memory_eval/test_readonly_mount_g266.py
# Description : Code G263/G265 publié sur un VRAI montage bind en lecture seule (unshare), synthétique (Claude, G266-9)
# Standard    : Eidolon Presentation Standard v1
# ==========================================================
"""Each scenario runs a child inside a private mount namespace (`unshare -m`): a synthetic canon is
bind-mounted READ-ONLY over an empty directory, then the PUBLISHED code runs on that mount (build_recall
with read_only_storage=True, check_storage). Nothing is mounted on the host namespace; no real corpus.
Where mount namespaces are not permitted, the tests are SKIPPED with that reason, never passed.

Unlike the intermediate profile of C188 (canon read-only + lock files re-mounted writable), here NO path
is writable in the mount: G263 opens the existing locks read-only."""
import json
from pathlib import Path
import shutil
import subprocess
import sys
import textwrap

import pytest

from tests.test_contextual_recall import backend, store

REPO = Path(__file__).resolve().parents[2]


def _namespaces_allowed():
    if not shutil.which("unshare"):
        return "unshare not installed"
    probe = subprocess.run(["unshare", "-m", "sh", "-c", "mount -t tmpfs none /mnt 2>&1 || exit 3"],
                           capture_output=True, text=True)
    return None if probe.returncode == 0 else f"mount namespace refused: {probe.stdout.strip() or probe.returncode}"


REASON = _namespaces_allowed()
pytestmark = [pytest.mark.skipif(REASON is not None, reason=str(REASON)),
              pytest.mark.skipif(not sys.platform.startswith("linux"), reason="Linux mount namespaces")]

CHILD = textwrap.dedent("""
    import errno, json, sys
    sys.path.insert(0, sys.argv[1])
    from pathlib import Path
    from services import memory_bridge as bridge
    root, action = Path(sys.argv[2]), sys.argv[3]
    out = {}
    try:
        open(root / "memory/persistent/probe", "w")
        out["write"] = "ALLOWED"
    except OSError as exc:
        out["write"] = errno.errorcode[exc.errno]
    if action == "check":
        out["check"] = bridge.check_storage(root)["state"]
    elif action == "recall":
        recall = bridge.build_recall(root, read_only_storage=True)
        out["items"] = len(recall.recall("power").items)
    elif action == "default":
        try:
            bridge.build_recall(root, read_only_storage=False).recall("power")
            out["default"] = "ok"
        except OSError as exc:
            out["default"] = errno.errorcode[exc.errno]
    print(json.dumps(out))
""")


def canon(tmp_path, *, threads=True):
    src = tmp_path / "src"
    data = backend(src)
    store(data, "a-power", content="power measurement")
    if threads:
        (src / "memory/persistent/threads").mkdir()
    from core.retrieval.contextual import ContextualRecall
    ContextualRecall(data).recall("power")                      # creates the lock files, as a writer would
    return src


def on_readonly_mount(src, action, tmp_path):
    mount = tmp_path / "ro"
    mount.mkdir(exist_ok=True)
    script = f"mount --bind {src} {mount} && mount -o remount,ro,bind {mount} && " \
             f"{sys.executable} -B -c \"$0\" {REPO} {mount} {action}"
    r = subprocess.run(["unshare", "-m", "sh", "-c", script, CHILD], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr[-2000:]
    return json.loads(r.stdout)


@pytest.mark.parametrize("threads", [False, True])
def test_published_readonly_recall_and_check_work_on_a_real_readonly_mount(tmp_path, threads):
    src = canon(tmp_path, threads=threads)
    assert on_readonly_mount(src, "recall", tmp_path) == {"write": "EROFS", "items": 1}
    assert on_readonly_mount(src, "check", tmp_path) == {"write": "EROFS", "check": "READY"}


def test_the_default_mode_still_fails_on_the_same_mount(tmp_path):
    """The historical contract (lock opened 'a+b') cannot run read-only: G263 is what makes it possible."""
    src = canon(tmp_path)
    assert on_readonly_mount(src, "default", tmp_path) == {"write": "EROFS", "default": "EROFS"}


@pytest.mark.parametrize("lock", ["memory/persistent/.write.lock", "memory/persistent/threads/.write.lock"])
def test_a_lock_that_disappeared_is_never_recreated_and_never_ready(tmp_path, lock):
    src = canon(tmp_path)
    (src / lock).unlink()
    result = on_readonly_mount(src, "check", tmp_path)
    assert result["check"] == "UNAVAILABLE" and not (src / lock).exists()


def test_a_writer_on_the_writable_path_makes_the_readonly_check_busy(tmp_path):
    src = canon(tmp_path)
    gate = tmp_path / "release"
    holder = subprocess.Popen([sys.executable, "-c", textwrap.dedent(f"""
        import sys, time, pathlib
        sys.path.insert(0, {str(REPO)!r})
        from core.persistence import exclusive_write
        with exclusive_write(pathlib.Path({str(src / 'memory/persistent')!r})):
            print("held", flush=True)
            while not pathlib.Path({str(gate)!r}).exists():
                time.sleep(0.01)
    """)], stdout=subprocess.PIPE, text=True)
    try:
        assert holder.stdout.readline().strip() == "held"
        assert on_readonly_mount(src, "check", tmp_path)["check"] == "BUSY"   # same inode across the mounts
    finally:
        gate.touch()
        holder.wait(5)
        holder.stdout.close()
    assert on_readonly_mount(src, "check", tmp_path)["check"] == "READY"
