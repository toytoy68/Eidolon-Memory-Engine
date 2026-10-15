# ==========================================================
# Projet      : Eidolon Memory Engine
# Organisation: Eidolon Core Technologies (ECT)
# Fichier     : tests/claude_memory_eval/test_receipt_numeric_review_g266.py
# Description : Contre-revue numérique G267 : bornes flottantes, gardes actifs, consommateur de rétention (G266-7)
# Standard    : Eidolon Presentation Standard v1
# ==========================================================
"""Distinct from Codex's test_receipt_numeric_g267.py; does not redo the seen-state review of G262-9."""
import math
import sys

import pytest

from tests.claude_memory_eval.alias_switch_receipt import (ReceiptRefused, make_receipt, retirement_facts,
                                                           verify_chain, verify_receipt)
from tests.claude_memory_eval.generation_retention import GenerationFacts, classify
from tests.claude_memory_eval.test_receipt_replay_state_g262 import ALIAS, G, R

FIELDS = {k: v for k, v in R.items() if k not in {"schema", "receipt_sha256"}}
LARGEST_INT_AS_FLOAT = int(sys.float_info.max)                # still representable
TOO_BIG = 2 ** 1024                                           # first power of two that overflows


def code(call):
    with pytest.raises(ReceiptRefused) as caught:
        call()
    return caught.value.code


def test_the_float_boundary_is_exact():
    assert verify_receipt(make_receipt(**dict(FIELDS, switched_at=LARGEST_INT_AS_FLOAT))) == R["switch_id"]
    assert code(lambda: make_receipt(**dict(FIELDS, switched_at=TOO_BIG))) == "RECEIPT_INVALID"


@pytest.mark.parametrize("value", [True, False, math.nan, math.inf, -1, -1e-300, "1800000000"])
def test_other_non_times_keep_their_public_refusal(value):
    assert code(lambda: make_receipt(**dict(FIELDS, switched_at=value))) == "RECEIPT_INVALID"


def test_huge_but_valid_times_keep_digest_replay_identity_and_order_guards():
    big = LARGEST_INT_AS_FLOAT
    first = make_receipt(**dict(FIELDS, switched_at=big - 2 ** 970))
    assert code(lambda: verify_receipt(dict(first, switched_at=big))) == "RECEIPT_DIGEST_MISMATCH"
    assert code(lambda: verify_receipt(first, seen_switch_ids={R["switch_id"]})) == "RECEIPT_REPLAYED"
    assert code(lambda: verify_receipt(dict(first, alias="other"))) in ("RECEIPT_INVALID", "RECEIPT_DIGEST_MISMATCH")
    second = make_receipt(**dict(FIELDS, switch_id="2" * 32, previous_generation=G[2], new_generation=G[3],
                                 observed_before=G[2], observed_after=G[3], switched_at=big - 2 ** 971))
    # Exact int comparison: big - 2**971 < big - 2**970, so time goes back even at this magnitude.
    assert code(lambda: verify_chain([first, second], alias=ALIAS, initial_generation=G[1])) == "CHAIN_TIME_REGRESSED"


def test_int_and_float_of_the_same_instant_are_distinct_receipts_but_each_verifies():
    as_int = make_receipt(**dict(FIELDS, switched_at=1_800_000_000))
    as_float = make_receipt(**dict(FIELDS, switched_at=1.8e9))
    assert as_int["receipt_sha256"] != as_float["receipt_sha256"]
    assert verify_receipt(as_int) == verify_receipt(as_float) == R["switch_id"]


def test_a_huge_valid_receipt_never_becomes_a_review_candidate():
    receipt = make_receipt(**dict(FIELDS, switched_at=10 ** 30))
    facts = retirement_facts([receipt], alias=ALIAS, initial_generation=G[1], observed_target=G[2])
    retired_at, audit = facts[G[1]]
    out = classify([GenerationFacts(G[1], ALIAS, False, True, True, 0, retired_at, audit),
                    GenerationFacts(G[2], ALIAS, True, True, True, 0, None, None)], now=1.8e9, grace_seconds=60)
    assert out[0].verdict == "KEEP_UNCERTAIN"                 # in the future for any real clock


@pytest.mark.parametrize("option", ["retired_at", "now", "epoch_window", "not_before", "grace_seconds"])
def test_the_retention_consumer_refuses_unrepresentable_times_without_a_raw_overflow(option):
    act = GenerationFacts(G[2], ALIAS, True, True, True, 0, None, None)
    old = GenerationFacts(G[1], ALIAS, False, True, True, 0, 1.7e9, "a" * 32)
    args = dict(now=1.8e9, grace_seconds=60)
    if option == "retired_at":
        old = GenerationFacts(G[1], ALIAS, False, True, True, 0, 10 ** 400, "a" * 32)
        assert classify([act, old], **args)[1].verdict == "KEEP_UNCERTAIN"
        return
    args[option] = (0, 10 ** 400) if option == "epoch_window" else 10 ** 400
    with pytest.raises(ValueError) as caught:
        classify([act, old], **args)
    assert type(caught.value) is ValueError                    # the public refusal, not OverflowError
