# ==========================================================
# Projet      : Eidolon Memory Engine
# Organisation: Eidolon Core Technologies (ECT)
# Fichier     : tests/claude_memory_eval/test_storage_usage_review_g268.py
# Description : Contre-revue G268 : erreurs d'usage 64 sans effet, compatibilité serveur, aide, abréviations (Claude)
# Standard    : Eidolon Presentation Standard v1
# ==========================================================
"""Each command runs in a subprocess through the G264 audit wrapper (sockets, write opens, mutations and
heavy imports recorded), extended here to record ANY open or listing under the canonical root. Synthetic
corpus only; no token is ever set, so server mode always stops at its token check, before binding."""
import json
import os
from pathlib import Path
import subprocess
import sys
import textwrap

import pytest

from services import memory_bridge as bridge
from tests.claude_memory_eval.test_storage_check_review_g264 import REPO, corpus

pytestmark = pytest.mark.skipif(not sys.platform.startswith("linux"), reason="Linux readonly storage contract")

WRAPPER = textwrap.dedent("""
    import json, os, runpy, sys
    root = os.environ["G268_ROOT"]
    events = []
    def hook(event, args):
        if event.startswith("socket."):
            events.append(event)
        elif event == "open" and isinstance(args[0], (str, bytes, os.PathLike)):
            mode, flags = args[1], args[2]
            if (mode and any(c in mode for c in "wax+")) or flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT):
                events.append("write-open")
            if os.fsdecode(args[0]).startswith(root):
                events.append("root-open")
        elif event in ("os.listdir", "os.scandir") and args and os.fsdecode(str(args[0])).startswith(root):
            events.append("root-listing")
        elif event in ("os.mkdir", "os.rename", "os.replace", "os.remove", "os.rmdir", "os.chmod", "os.truncate"):
            events.append(event)
    sys.addaudithook(hook)
    sys.argv = ["memory_bridge"] + sys.argv[1:]
    code = 0
    try:
        runpy.run_module("services.memory_bridge", run_name="__main__")
    except SystemExit as exc:
        code = exc.code if isinstance(exc.code, int) else 1
    heavy = sorted(m for m in ("torch", "sentence_transformers", "transformers", "core.retrieval.reranked")
                   if m in sys.modules)
    sys.stderr.write("\\n@@AUDIT@@" + json.dumps(dict(events=sorted(set(events)), heavy=heavy)))
    sys.exit(code)
""")


def run(root, *args):
    env = {k: v for k, v in os.environ.items() if k != "EIDOLON_MEMORY_BRIDGE_TOKEN"}
    env["G268_ROOT"] = str(root)
    r = subprocess.run([sys.executable, "-B", "-c", WRAPPER, *args], cwd=REPO, env=env,
                       capture_output=True, text=True, timeout=30)
    err, _, audit = r.stderr.partition("\n@@AUDIT@@")
    return r.returncode, r.stdout, err, json.loads(audit)


R = "<root>"                                                       # replaced by the synthetic root


def argv(root, args):
    return [str(root) if a == R else a.replace("<root>", str(root)) for a in args]


USAGE = [                                                           # diagnostic intent + usage error -> 64
    ["--check-storage"],
    ["--check-storage", "--root"],
    ["--root", R, "--check-storage", "--port", "18765"],
    ["--root", R, "--check-storage", "--port=1"],
    ["--root", R, "--check-storage", "--reranker-cache", R],
    ["--root", R, "--check-storage", "--port", "bad"],
    ["--root", R, "--check-storage", "extra"],
    ["--root", R, "--check-storage", "-x"],
    ["--root", R, "--check-storage", "--", "x"],
    ["--root", R, "--ch=1"],
    ["--root", R, "--re", R, "--che"],                              # ambiguous --re
    ["--root", "--check-storage"],                                  # --root given no value
    ["--root", R, "--port", "--c"],
]


@pytest.mark.parametrize("args", USAGE, ids=[" ".join(a) for a in USAGE])
def test_a_diagnostic_usage_error_is_64_and_touches_nothing(tmp_path, args):
    root = corpus(tmp_path)
    code, out, err, audit = run(root, *argv(root, args))
    assert code == 64 and out == "" and "usage:" in err
    assert audit == {"events": [], "heavy": []}                     # no socket, write, mutation, root access


DIAGNOSTIC = [["--check-storage"], ["--check-storag"], ["--che"], ["--c"], ["--read-only-storage", "--c"]]


@pytest.mark.parametrize("flag", DIAGNOSTIC, ids=[" ".join(a) for a in DIAGNOSTIC])
def test_every_unique_abbreviation_still_runs_the_diagnostic(tmp_path, flag):
    root = corpus(tmp_path)
    code, out, err, audit = run(root, "--root", str(root), *flag)
    assert code == 0 and json.loads(out)["state"] == "READY" and err == ""
    assert "write-open" not in audit["events"] and audit["heavy"] == []


SERVER = [                                                          # no diagnostic intent: argparse's 2, unchanged
    [],
    ["--root", R],                                                  # stops at the (absent) token check
    ["--root", R, "--port", "bad"],
    ["--root", R, "--port", "80"],
    ["--root=--check-storage"],                                    # a VALUE that looks like the flag
    ["--root", R, "--", "--check-storage"],                        # after `--`: not an option
    ["--root", R, "--check-storagex"],                             # not a prefix of the flag
    ["--root", R, "-check-storage"],
    ["--root", R, "---check-storage"],
    ["--root", R, "--CHECK-STORAGE"],
    ["--root", R, "-"],                                             # a lone dash is a prefix of nothing
]


@pytest.mark.parametrize("args", SERVER, ids=[" ".join(a) or "(none)" for a in SERVER])
def test_server_mode_usage_errors_keep_code_2_and_never_start(tmp_path, args):
    root = corpus(tmp_path)
    code, out, err, audit = run(root, *argv(root, args))
    assert code == 2 and out == "" and "error:" in err
    assert not {"socket.bind", "socket.listen"} & set(audit["events"]) and audit["heavy"] == []


@pytest.mark.parametrize("args", [["-h"], ["--help"], ["--check-storage", "-h"], ["--c", "--help"],
                                  ["--check-storage", "--port", "1", "-h"]])
def test_help_is_0_on_stdout_and_touches_nothing(tmp_path, args):
    root = corpus(tmp_path)
    code, out, err, audit = run(root, *args)
    assert code == 0 and out.startswith("usage:") and err == ""
    assert audit == {"events": [], "heavy": []}


def test_64_is_distinct_from_every_diagnostic_state_and_from_server_usage():
    assert 64 not in bridge.STORAGE_CHECK_EXIT.values() and 2 in bridge.STORAGE_CHECK_EXIT.values()
    assert len(set(bridge.STORAGE_CHECK_EXIT.values())) == len(bridge.STORAGE_CHECK_EXIT)
