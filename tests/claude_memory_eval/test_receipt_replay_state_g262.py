# ==========================================================
# Projet      : Eidolon Memory Engine
# Organisation: Eidolon Core Technologies (ECT)
# Fichier     : tests/claude_memory_eval/test_receipt_replay_state_g262.py
# Description : Reçus : état de rejeu invalide, fenêtres géantes, consommation durable concurrente (Claude, G262-9)
# Standard    : Eidolon Presentation Standard v1
# ==========================================================
"""Synthetic receipts and temporary directories only; no deletion permission is ever produced."""
import os
from pathlib import Path
import subprocess
import sys
import textwrap

import pytest

from tests.claude_memory_eval.alias_switch_receipt import (ReceiptRefused, make_receipt, retirement_facts,
                                                           verify_chain, verify_receipt)
from tests.claude_memory_eval.receipt_seen_store import DirectorySeenStore

ALIAS = "eidolon_x"
G = {n: f"{ALIAS}__{n:032x}" for n in range(1, 4)}
REPO = Path(__file__).resolve().parents[2]
R = make_receipt(switch_id="1" * 32, alias=ALIAS, previous_generation=G[1], new_generation=G[2],
                 new_descriptor_sha256="d" * 64, manifest_sha256="a" * 64, switched_at=1.8e9,
                 observed_before=G[1], observed_after=G[2])


def code(call):
    with pytest.raises(ReceiptRefused) as caught:
        call()
    return caught.value.code


@pytest.mark.parametrize("window", [(0, 10 ** 400), (10 ** 400, 10 ** 401), (-(10 ** 400), 0), (True, 2e9),
                                    (0, float("inf")), [0, 2e9], (2e9, 1e9)])
def test_huge_or_malformed_windows_get_a_stable_code(window):
    assert code(lambda: verify_chain([R], alias=ALIAS, initial_generation=G[1], epoch_window=window)) \
        == "RECEIPT_INVALID"
    assert verify_chain([R], alias=ALIAS, initial_generation=G[1], epoch_window=(0, 10 ** 30)) == G[2]


@pytest.mark.parametrize("seen", ["1" * 32, b"x", None, {"1" * 32: 0}, (x for x in ["1" * 32]), {"X"},
                                  ["1" * 31], [1], frozenset({"1" * 32, None})])
def test_an_invalid_seen_set_is_refused_never_ignored(seen):
    # A string used to become a set of characters: replay detection silently off.
    for call in (lambda: verify_receipt(R, seen_switch_ids=seen),
                 lambda: verify_chain([R], alias=ALIAS, initial_generation=G[1], seen_switch_ids=seen),
                 lambda: retirement_facts([R], alias=ALIAS, initial_generation=G[1], observed_target=G[2],
                                          seen_switch_ids=seen)):
        assert code(call) == "RECEIPT_INVALID_SEEN"


@pytest.mark.parametrize("kind", [set, frozenset, list, tuple])
def test_valid_collections_still_detect_replay(kind):
    assert code(lambda: verify_chain([R], alias=ALIAS, initial_generation=G[1],
                                     seen_switch_ids=kind(["1" * 32]))) == "RECEIPT_REPLAYED"


def test_durable_consumption_is_once_and_survives_a_new_store(tmp_path):
    store = DirectorySeenStore(tmp_path)
    assert store.consume(R) == "1" * 32
    assert code(lambda: store.consume(R)) == "RECEIPT_REPLAYED"
    assert code(lambda: DirectorySeenStore(tmp_path).consume(R)) == "RECEIPT_REPLAYED"   # "after restart"
    assert DirectorySeenStore(tmp_path).consumed() == {"1" * 32}
    assert os.listdir(tmp_path) == ["1" * 32] and (tmp_path / ("1" * 32)).stat().st_size == 0


def test_an_unsafe_store_directory_is_refused(tmp_path):
    shared = tmp_path / "shared"
    shared.mkdir()
    shared.chmod(0o777)
    assert code(lambda: DirectorySeenStore(shared)) == "RECEIPT_STORE_UNSAFE"
    (tmp_path / "link").symlink_to(tmp_path)
    assert code(lambda: DirectorySeenStore(tmp_path / "link")) == "RECEIPT_STORE_UNSAFE"


def test_concurrent_processes_consume_an_id_exactly_once(tmp_path):
    script = textwrap.dedent(f"""
        import sys
        sys.path.insert(0, {str(REPO)!r})
        from tests.claude_memory_eval.receipt_seen_store import DirectorySeenStore
        from tests.claude_memory_eval.alias_switch_receipt import ReceiptRefused
        import tests.claude_memory_eval.test_receipt_replay_state_g262 as t
        try:
            DirectorySeenStore({str(tmp_path)!r}).consume(t.R)
            print("won")
        except ReceiptRefused as e:
            print(e.code)
    """)
    procs = [subprocess.Popen([sys.executable, "-c", script], stdout=subprocess.PIPE, text=True, cwd=REPO)
             for _ in range(12)]
    outcomes = []
    for p in procs:
        out, _ = p.communicate(timeout=60)
        outcomes.append(out.strip())
    assert outcomes.count("won") == 1 and set(outcomes) == {"won", "RECEIPT_REPLAYED"}, outcomes


def test_the_pure_receipt_module_still_has_no_file_access():
    import tests.claude_memory_eval.alias_switch_receipt as module
    source = Path(module.__file__).read_text(encoding="utf-8")
    assert "open(" not in source and "import os" not in source
