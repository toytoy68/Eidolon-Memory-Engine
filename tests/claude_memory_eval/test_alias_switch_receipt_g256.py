# ==========================================================
# Projet      : Eidolon Memory Engine
# Organisation: Eidolon Core Technologies (ECT)
# Fichier     : tests/claude_memory_eval/test_alias_switch_receipt_g256.py
# Description : Reçu pur de bascule d'alias : rejeu, reçu incomplet, chaîne, lien avec la rétention (G256-3)
# Standard    : Eidolon Presentation Standard v1
# ==========================================================
"""Synthetic fixture only: no Qdrant, no journal file, no deletion."""
import pytest

from tests.claude_memory_eval.alias_switch_receipt import (ReceiptRefused, make_receipt, retirement_facts,
                                                           verify_chain, verify_receipt)
from tests.claude_memory_eval.generation_retention import GenerationFacts, classify

ALIAS = "eidolon_x"
G = {n: f"{ALIAS}__{n:032x}" for n in range(1, 5)}


def receipt(n, old, new, at, **over):
    fields = dict(switch_id=f"{n:032x}", alias=ALIAS, previous_generation=G[old], new_generation=G[new],
                  new_descriptor_sha256="d" * 64, manifest_sha256="a" * 64,
                  switched_at=at, observed_before=G[old], observed_after=G[new])
    fields.update(over)
    return make_receipt(**fields)


def refused(code, value, **kwargs):
    with pytest.raises(ReceiptRefused) as caught:
        verify_receipt(value, **kwargs)
    assert caught.value.code == code


def test_a_receipt_verifies_and_every_field_is_bound_by_its_digest():
    r = receipt(1, 1, 2, 1000)
    assert verify_receipt(r) == r["switch_id"]
    for change in [dict(switch_id="f" * 32), dict(previous_generation=G[3], observed_before=G[3]),
                   dict(new_generation=G[3], observed_after=G[3]), dict(new_descriptor_sha256="e" * 64),
                   dict(manifest_sha256="b" * 64), dict(switched_at=1001)]:
        refused("RECEIPT_DIGEST_MISMATCH", dict(r, **change))


def test_incomplete_extra_and_replayed_receipts_are_refused():
    r = receipt(1, 1, 2, 1000)
    refused("RECEIPT_INCOMPLETE", {k: v for k, v in r.items() if k != "receipt_sha256"})
    refused("RECEIPT_INCOMPLETE", {k: v for k, v in r.items() if k != "manifest_sha256"})
    refused("RECEIPT_UNEXPECTED_FIELD", dict(r, text="private"))
    refused("RECEIPT_REPLAYED", r, seen_switch_ids={r["switch_id"]})
    refused("RECEIPT_INVALID", [r])


def test_a_switch_must_be_observed_and_real():
    with pytest.raises(ReceiptRefused, match="SWITCH_NOT_OBSERVED"):
        receipt(1, 1, 2, 1000, observed_after=G[1])       # alias read back still on the old generation
    with pytest.raises(ReceiptRefused, match="SWITCH_NOT_OBSERVED"):
        receipt(1, 1, 2, 1000, observed_before=G[3])      # somebody else switched in between
    with pytest.raises(ReceiptRefused, match="RECEIPT_NOT_A_SWITCH"):
        receipt(1, 1, 1, 1000)
    for bad in (dict(switched_at=float("nan")), dict(switched_at=True), dict(alias="Other"),
                dict(switch_id="X" * 32), dict(new_descriptor_sha256="d" * 63)):
        with pytest.raises(ReceiptRefused):
            receipt(1, 1, 2, 1000, **bad)


def test_the_chain_detects_replay_gaps_other_aliases_and_time_going_back():
    a, b = receipt(1, 1, 2, 1000), receipt(2, 2, 3, 2000)
    assert verify_chain([a, b], alias=ALIAS, initial_generation=G[1]) == G[3]
    for chain, code in [([a, a], "RECEIPT_REPLAYED"), ([b], "CHAIN_BROKEN"),
                        ([a, receipt(2, 2, 3, 999)], "CHAIN_TIME_REGRESSED")]:
        with pytest.raises(ReceiptRefused) as caught:
            verify_chain(chain, alias=ALIAS, initial_generation=G[1])
        assert caught.value.code == code
    with pytest.raises(ReceiptRefused, match="RECEIPT_OTHER_ALIAS"):
        verify_chain([a], alias="other", initial_generation=G[1])


def test_retirement_facts_feed_the_classifier_only_from_a_chain_matching_the_live_alias():
    chain = [receipt(1, 1, 2, 1000), receipt(2, 2, 3, 2000), receipt(3, 3, 2, 3000)]  # 2 is reactivated
    facts = retirement_facts(chain, alias=ALIAS, initial_generation=G[1], observed_target=G[2])
    assert facts == {G[1]: (1000, f"{1:032x}"), G[3]: (3000, f"{3:032x}")}
    twice = chain + [receipt(4, 2, 3, 3500)]  # 2 retired again: only its latest retirement counts
    assert retirement_facts(twice, alias=ALIAS, initial_generation=G[1], observed_target=G[3]) == \
        {G[1]: (1000, f"{1:032x}"), G[2]: (3500, f"{4:032x}")}
    # The alias read now disagrees with the chain: nothing is proven.
    assert retirement_facts(chain, alias=ALIAS, initial_generation=G[1], observed_target=G[3]) == {}

    def fact(name, target):
        retired_at, audit = facts.get(name, (None, None))
        return GenerationFacts(name, ALIAS, target, True, True, 0, retired_at, audit)
    out = {v.name: v.verdict for v in classify([fact(G[1], False), fact(G[2], True), fact(G[3], False)],
                                               now=4000, grace_seconds=1800)}
    assert out == {G[1]: "REVIEW_CANDIDATE", G[2]: "KEEP_ACTIVE", G[3]: "KEEP_RECENT"}


def test_the_module_has_no_side_effect_surface():
    import tests.claude_memory_eval.alias_switch_receipt as module
    from pathlib import Path
    source = Path(module.__file__).read_text(encoding="utf-8")
    for forbidden in ("open(", "delete", "drop", "qdrant_client", "time.", "datetime"):
        assert forbidden not in source.replace("no file", "")
