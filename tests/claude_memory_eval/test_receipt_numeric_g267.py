# ==========================================================
# Projet      : Eidolon Memory Engine
# Organisation: Eidolon Core Technologies (ECT)
# Fichier     : tests/claude_memory_eval/test_receipt_numeric_g267.py
# Description : Independent bounds for experimental receipt timestamps.
# Standard    : Eidolon Presentation Standard v1
# ==========================================================
"""Synthetic receipts only; no alias switch or retirement authorization."""
import pytest

from tests.claude_memory_eval.alias_switch_receipt import (
    ReceiptRefused, make_receipt, verify_receipt, verify_chain, retirement_facts,
)
from tests.claude_memory_eval.test_receipt_replay_state_g262 import R, ALIAS, G


@pytest.mark.parametrize('instant', [10 ** 400, -(10 ** 400)], ids=['huge-positive', 'huge-negative'])
@pytest.mark.parametrize('entry', ['make', 'verify', 'chain', 'retirement'])
def test_unrepresentable_timestamp_has_public_refusal(instant, entry):
    receipt = dict(R, switched_at=instant)
    with pytest.raises(ReceiptRefused, match='^RECEIPT_INVALID$'):
        if entry == 'make':
            make_receipt(**{k: v for k, v in receipt.items() if k not in {'schema', 'receipt_sha256'}})
        elif entry == 'verify':
            verify_receipt(receipt)
        elif entry == 'chain':
            verify_chain([receipt], alias=ALIAS, initial_generation=G[1])
        else:
            retirement_facts([receipt], alias=ALIAS, initial_generation=G[1], observed_target=G[2])


def test_finite_large_timestamp_stays_subject_to_digest_and_explicit_window():
    fields = {k: v for k, v in R.items() if k not in {'schema', 'receipt_sha256'}}
    receipt = make_receipt(**dict(fields, switched_at=10 ** 30))
    assert verify_receipt(receipt) == R['switch_id']
    with pytest.raises(ReceiptRefused, match='^RECEIPT_TIME_IMPLAUSIBLE$'):
        verify_chain([receipt], alias=ALIAS, initial_generation=G[1], epoch_window=(0, 2e9))
    with pytest.raises(ReceiptRefused, match='^RECEIPT_DIGEST_MISMATCH$'):
        verify_receipt(dict(receipt, switched_at=10 ** 30 + 1))
