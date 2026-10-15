# ==========================================================
# Projet      : Eidolon Memory Engine
# Organisation: Eidolon Core Technologies (ECT)
# Fichier     : tests/claude_memory_eval/test_alias_receipt_policies_g258.py
# Description : Reçu de bascule et rétention : cohérence entre politiques, faux alias, rejeu (Claude, G258-8)
# Standard    : Eidolon Presentation Standard v1
# ==========================================================
"""Synthetic only. The receipt is evidence for a human review, never a permission to delete."""
import pytest

from tests.claude_memory_eval.alias_switch_receipt import (ReceiptRefused, make_receipt, retirement_facts,
                                                           verify_chain)
from tests.claude_memory_eval.generation_retention import VERDICTS, GenerationFacts, classify

ALIAS = "eidolon_x"
G = {n: f"{ALIAS}__{n:032x}" for n in range(1, 6)}
T0 = 1_800_000_000
WINDOW = (946_684_800.0, 4_102_444_800.0)


def receipt(n, old, new, at, alias=ALIAS, gens=G):
    return make_receipt(switch_id=f"{n:032x}", alias=alias, previous_generation=gens[old], new_generation=gens[new],
                        new_descriptor_sha256="d" * 64, manifest_sha256="a" * 64, switched_at=at,
                        observed_before=gens[old], observed_after=gens[new])


def code(call):
    with pytest.raises(ReceiptRefused) as caught:
        call()
    return caught.value.code


def facts_for(chain, target, names, **options):
    proven = retirement_facts(chain, alias=ALIAS, initial_generation=G[1], observed_target=G[target], **options)
    return [GenerationFacts(G[n], ALIAS, n == target, True, True, 0, *proven.get(G[n], (None, None)))
            for n in names]


def test_false_anchors_are_refused():
    chain = [receipt(1, 1, 2, T0)]
    assert code(lambda: verify_chain(chain, alias=ALIAS, initial_generation="whatever")) == "RECEIPT_INVALID"
    assert code(lambda: retirement_facts(chain, alias=ALIAS, initial_generation=G[1],
                                         observed_target="x")) == "RECEIPT_INVALID"
    other = "other__" + "1" * 32
    assert code(lambda: verify_chain(chain, alias=ALIAS, initial_generation=other)) == "RECEIPT_OTHER_ALIAS"
    assert code(lambda: retirement_facts([], alias=ALIAS, initial_generation=G[1],
                                         observed_target=other)) == "RECEIPT_OTHER_ALIAS"


def test_generations_of_another_alias_never_mix_into_this_chain():
    O = {n: f"other__{n:032x}" for n in range(1, 3)}
    mixed = [receipt(1, 1, 2, T0), receipt(2, 1, 2, T0 + 1, alias="other", gens=O)]
    assert code(lambda: verify_chain(mixed, alias=ALIAS, initial_generation=G[1])) == "RECEIPT_OTHER_ALIAS"
    # A generation of this alias that no receipt mentions keeps its uncertainty.
    out = classify(facts_for([receipt(1, 1, 2, T0)], 2, [1, 2, 5]), now=T0 + 10_000, grace_seconds=60)
    assert [v.verdict for v in out] == ["REVIEW_CANDIDATE", "KEEP_ACTIVE", "KEEP_UNCERTAIN"]


def test_a_receipt_replayed_into_a_later_verification_is_refused_with_the_host_seen_set():
    a = receipt(1, 1, 2, T0)
    consumed = {a["switch_id"]}                     # what the host recorded after the first verification
    assert code(lambda: verify_chain([a], alias=ALIAS, initial_generation=G[1],
                                     seen_switch_ids=consumed)) == "RECEIPT_REPLAYED"
    assert code(lambda: retirement_facts([a], alias=ALIAS, initial_generation=G[1], observed_target=G[2],
                                         seen_switch_ids=consumed)) == "RECEIPT_REPLAYED"


@pytest.mark.parametrize("at", [0, 1, 1.8e12])
def test_receipt_and_classifier_use_the_same_epoch_window(at):
    chain = [receipt(1, 1, 2, at)]
    assert code(lambda: retirement_facts(chain, alias=ALIAS, initial_generation=G[1], observed_target=G[2],
                                         epoch_window=WINDOW)) == "RECEIPT_TIME_IMPLAUSIBLE"
    # Without the window on the receipt, the classifier's own window still keeps the generation.
    out = classify(facts_for(chain, 2, [1, 2]), now=T0, grace_seconds=60, epoch_window=WINDOW)
    assert out[0].verdict.startswith("KEEP_")


def test_replaying_under_another_clock_or_grace_is_monotonic_and_never_more_than_a_review():
    chain = [receipt(1, 1, 2, T0), receipt(2, 2, 3, T0 + 500)]
    seen = []
    for now in range(T0 - 100, T0 + 4000, 50):
        for grace in (1, 600, 3600):
            if now < T0 + 500:
                continue                                          # the clock may not precede the chain
            verdicts = [v.verdict for v in classify(facts_for(chain, 3, [1, 2, 3]), now=now, grace_seconds=grace,
                                                    epoch_window=WINDOW, not_before=T0 + 500)]
            assert verdicts[2] == "KEEP_ACTIVE" and set(verdicts) <= set(VERDICTS)
            seen.append((grace, now, tuple(verdicts)))
    for grace in (1, 600, 3600):
        series = [v for g, _, v in seen if g == grace]
        flipped = [any(x == "REVIEW_CANDIDATE" for x in v[:2]) for v in series]
        assert flipped == sorted(flipped)                        # once a candidate, it stays one as time passes
    with pytest.raises(ValueError, match="clock regressed"):
        classify(facts_for(chain, 3, [1, 2, 3]), now=T0 + 400, grace_seconds=1, not_before=T0 + 500)


def test_the_receipt_never_becomes_a_deletion_permission():
    assert "REVIEW_CANDIDATE" == VERDICTS[-1] and not any("DELETE" in v or "DROP" in v for v in VERDICTS)
    import tests.claude_memory_eval.alias_switch_receipt as module
    assert not [name for name in dir(module) if "delete" in name.lower() or "drop" in name.lower()]
