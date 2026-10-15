# ==========================================================
# Projet      : Eidolon Memory Engine
# Organisation: Eidolon Core Technologies (ECT)
# Fichier     : tests/claude_memory_eval/test_retention_inputs_g256.py
# Description : Entrées et cohérence temporelle du classificateur de rétention (Claude, G256-1/2)
# Standard    : Eidolon Presentation Standard v1
# ==========================================================
"""Pure, synthetic. The single property under test: no ambiguous, malformed or temporally
inconsistent fact may ever produce REVIEW_CANDIDATE. Each case was a REVIEW_CANDIDATE (or a crash)
on the G252 classifier."""
import math

import pytest

from tests.claude_memory_eval.generation_retention import GenerationFacts, classify

ALIAS = "eidolon_x"
NOW = 1_800_000_000.0           # synthetic Unix seconds (2027)
WINDOW = (946_684_800.0, 4_102_444_800.0)  # host-supplied plausibility window (2000-01-01, 2100-01-01)


def gen(n, alias=ALIAS, **over):
    values = dict(name=f"{alias}__{n:032x}", alias=alias, is_alias_target=False, descriptor_valid=True,
                  complete=True, readers=0, retired_at=NOW - 7200, audit_reference="audit-1")
    values.update(over)
    return GenerationFacts(**values)


ACTIVE = gen(1, is_alias_target=True)


def verdict(fact, *others, now=NOW, grace=3600, **options):
    out = classify([ACTIVE, *others, fact], now=now, grace_seconds=grace, **options)
    return out[-1].verdict, out[-1].reasons


def test_the_reference_case_is_a_candidate():
    assert verdict(gen(2))[0] == "REVIEW_CANDIDATE"


@pytest.mark.parametrize("field, value", [
    ("readers", False), ("readers", 0.0), ("readers", -1), ("readers", math.nan), ("readers", "0"),
    ("descriptor_valid", "no"), ("descriptor_valid", 1), ("complete", 1), ("complete", "false"),
    ("complete", math.nan), ("is_alias_target", "true"), ("is_alias_target", 0),
    ("audit_reference", ""), ("audit_reference", " "), ("audit_reference", 0), ("audit_reference", "a\nb"),
    ("retired_at", True), ("retired_at", math.nan), ("retired_at", math.inf), ("retired_at", -5.0),
    ("retired_at", "1700000000"),
])
def test_an_ambiguous_fact_is_never_a_candidate(field, value):
    result, reasons = verdict(gen(2, **{field: value}))
    assert result.startswith("KEEP_"), (field, value, result, reasons)


def test_a_malformed_alias_or_name_keeps_instead_of_crashing():
    for fact in (gen(2, alias=None, name=f"None__{2:032x}"), gen(2, name=["list"]), gen(2, alias="")):
        assert verdict(fact)[0] == "KEEP_UNCERTAIN"


def test_another_alias_target_does_not_vouch_for_this_alias():
    assert verdict(gen(2, alias="other"))[0] == "KEEP_UNCERTAIN"
    assert verdict(gen(2, alias="other"), gen(3, alias="other", is_alias_target=True))[0] == "REVIEW_CANDIDATE"


def test_duplicates_and_foreign_objects_are_refused_and_generators_are_complete():
    with pytest.raises(ValueError):
        classify([ACTIVE, gen(2), gen(2, readers=1)], now=NOW, grace_seconds=1)
    with pytest.raises(ValueError):
        classify([ACTIVE, dict(name="x")], now=NOW, grace_seconds=1)
    assert [v.verdict for v in classify((f for f in (ACTIVE, gen(2))), now=NOW, grace_seconds=1)] == \
        ["KEEP_ACTIVE", "REVIEW_CANDIDATE"]


# G256-2: time.

def test_retirement_in_the_future_or_after_a_clock_step_back_is_kept():
    assert verdict(gen(2, retired_at=NOW + 1)) == ("KEEP_UNCERTAIN", ("RETIREMENT_IN_FUTURE",))
    with pytest.raises(ValueError, match="clock regressed"):
        classify([ACTIVE, gen(2)], now=NOW, grace_seconds=1, not_before=NOW + 1)
    assert classify([ACTIVE, gen(2)], now=NOW, grace_seconds=1, not_before=NOW)[1].verdict == "REVIEW_CANDIDATE"
    with pytest.raises(ValueError):
        classify([ACTIVE], now=NOW, grace_seconds=1, not_before=math.nan)


def test_exact_grace_boundaries():
    assert verdict(gen(2, retired_at=NOW - 3600))[0] == "REVIEW_CANDIDATE"   # age == grace: inclusive
    assert verdict(gen(2, retired_at=NOW - 3599.999))[0] == "KEEP_RECENT"
    assert verdict(gen(2, retired_at=NOW))[0] == "KEEP_RECENT"               # retired this instant
    assert verdict(gen(2, retired_at=1), now=3601)[0] == "REVIEW_CANDIDATE"   # integers too


def test_mixed_units_are_refused_with_a_host_window():
    # Clock in milliseconds, retirement in seconds: without a window this is indistinguishable
    # from a very old retirement (documented limit); with the host window it is refused.
    assert verdict(gen(2, retired_at=1.7e9), now=1.8e12)[0] == "REVIEW_CANDIDATE"
    with pytest.raises(ValueError, match="implausible clock"):
        classify([ACTIVE, gen(2, retired_at=1.7e9)], now=1.8e12, grace_seconds=1, epoch_window=WINDOW)
    # Clock in seconds, retirement in milliseconds: always in the future, kept.
    assert verdict(gen(2, retired_at=1.7e12))[0] == "KEEP_UNCERTAIN"
    # Retirement before the plausibility floor (epoch sentinel) is not a proof.
    assert verdict(gen(2, retired_at=0.0), epoch_window=WINDOW) == \
        ("KEEP_UNCERTAIN", ("RETIREMENT_TIME_IMPLAUSIBLE",))
    assert verdict(gen(2), epoch_window=WINDOW)[0] == "REVIEW_CANDIDATE"


@pytest.mark.parametrize("options", [
    dict(now="2027-01-15T08:00:00+00:00"), dict(now=True), dict(now=-1), dict(now=math.inf),
    dict(grace_seconds=True), dict(grace_seconds=math.nan), dict(epoch_window=(1, 0)),
    dict(epoch_window=[0, 1]), dict(epoch_window=(0, math.inf)),
])
def test_public_refusals_are_value_errors(options):
    args = dict(now=NOW, grace_seconds=3600)
    args.update(options)
    with pytest.raises(ValueError):
        classify([ACTIVE, gen(2)], **args)
