# ==========================================================
# Projet      : Eidolon Memory Engine
# Organisation: Eidolon Core Technologies (ECT)
# Fichier     : tests/claude_memory_eval/test_receipt_store_failures_g266.py
# Description : Consommation durable de reçu : échecs après création, répertoire substitué ou élargi (Claude, G266-6)
# Standard    : Eidolon Presentation Standard v1
# ==========================================================
"""Synthetic receipts and temporary directories. Failures are injected; nothing real is deleted."""
import os

import pytest

import tests.claude_memory_eval.receipt_seen_store as store_module
from tests.claude_memory_eval.alias_switch_receipt import ReceiptRefused
from tests.claude_memory_eval.receipt_seen_store import DirectorySeenStore
from tests.claude_memory_eval.test_receipt_replay_state_g262 import R

ID = "1" * 32


def code(call):
    with pytest.raises(ReceiptRefused) as caught:
        call()
    return caught.value.code


@pytest.mark.parametrize("failing", [1, 2])                       # 1: fsync of the mark, 2: of the directory
def test_a_failure_after_creation_is_ambiguous_keeps_the_mark_and_blocks_reuse(tmp_path, monkeypatch, failing):
    store = DirectorySeenStore(tmp_path)
    calls = []
    real = os.fsync

    def flaky(fd):
        calls.append(fd)
        if len(calls) == failing:
            raise OSError(5, "synthetic EIO")
        return real(fd)
    monkeypatch.setattr(store_module.os, "fsync", flaky)
    assert code(lambda: store.consume(R)) == "RECEIPT_CONSUMED_UNCONFIRMED"
    monkeypatch.undo()
    assert (tmp_path / ID).exists()                                # never removed
    assert code(lambda: store.consume(R)) == "RECEIPT_REPLAYED"     # a retry cannot consume it twice
    assert store.consumed() == {ID}


def test_a_directory_replaced_after_construction_is_refused(tmp_path):
    directory = tmp_path / "seen"
    directory.mkdir(mode=0o700)
    store = DirectorySeenStore(directory)
    directory.rename(tmp_path / "old")
    directory.mkdir(mode=0o700)                                    # same path, other inode: empty history
    assert code(lambda: store.consume(R)) == "RECEIPT_STORE_CHANGED"
    assert code(lambda: store.consumed()) == "RECEIPT_STORE_CHANGED"
    assert not (directory / ID).exists()


def test_a_directory_replaced_by_a_link_is_refused(tmp_path):
    directory = tmp_path / "seen"
    directory.mkdir(mode=0o700)
    store = DirectorySeenStore(directory)
    directory.rename(tmp_path / "old")
    directory.symlink_to(tmp_path / "old")                          # even pointing at the original
    assert code(lambda: store.consume(R)) == "RECEIPT_STORE_CHANGED"


def test_rights_widened_after_construction_are_refused(tmp_path):
    directory = tmp_path / "seen"
    directory.mkdir(mode=0o700)
    store = DirectorySeenStore(directory)
    directory.chmod(0o777)
    assert code(lambda: store.consume(R)) == "RECEIPT_STORE_UNSAFE"
    directory.chmod(0o700)
    assert store.consume(R) == ID


def test_construction_refuses_links_and_missing_directories(tmp_path):
    (tmp_path / "alias").symlink_to(tmp_path)
    assert code(lambda: DirectorySeenStore(tmp_path / "alias")) == "RECEIPT_STORE_UNSAFE"
    assert code(lambda: DirectorySeenStore(tmp_path / "absent")) == "RECEIPT_STORE_UNSAFE"


def test_a_planted_file_with_an_id_name_counts_as_consumed(tmp_path):
    """Documented limit: anyone able to write in the directory can block an id (never unblock one)."""
    store = DirectorySeenStore(tmp_path)
    (tmp_path / ID).touch()
    assert code(lambda: store.consume(R)) == "RECEIPT_REPLAYED"
