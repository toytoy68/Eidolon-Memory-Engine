# ==========================================================
# Projet      : Eidolon Memory Engine
# Organisation: Eidolon Core Technologies (ECT)
# Fichier     : tests/claude_memory_eval/test_generation_retention_g252.py
# Description : Tests du classificateur expérimental de rétention (Claude, G252-7)
# Standard    : Eidolon Presentation Standard v1
# ==========================================================
import pytest

from tests.claude_memory_eval.generation_retention import GenerationFacts, classify

ALIAS = "eidolon_x"


def gen(n, **over):
    values = dict(name=f"{ALIAS}__{n:032x}", alias=ALIAS, is_alias_target=False, descriptor_valid=True,
                  complete=True, readers=0, retired_at=0.0, audit_reference="audit-1")
    values.update(over)
    return GenerationFacts(**values)


def verdicts(facts, now=10_000.0, grace=3600):
    return {v.name[-1]: v.verdict for v in classify(facts, now=now, grace_seconds=grace)}


def test_the_active_generation_is_never_a_candidate():
    out = verdicts([gen(1, is_alias_target=True), gen(2)])
    assert out == {"1": "KEEP_ACTIVE", "2": "REVIEW_CANDIDATE"}


def test_any_unknown_fact_keeps_the_generation():
    cases = [gen(2, readers=None), gen(3, descriptor_valid=None), gen(4, complete=None),
             gen(5, retired_at=None), gen(6, audit_reference=None), gen(7, retired_at=20_000.0)]
    out = verdicts([gen(1, is_alias_target=True), *cases])
    assert all(v.startswith("KEEP_") for k, v in out.items())


def test_uncertain_alias_state_protects_everything():
    for facts in ([gen(1, is_alias_target=None), gen(2)], [gen(1), gen(2)],
                  [gen(1, is_alias_target=True), gen(2, is_alias_target=True)]):
        assert all(v.verdict.startswith("KEEP_") for v in classify(facts, now=10_000.0, grace_seconds=3600))


def test_grace_readers_and_failed_builds():
    out = verdicts([gen(1, is_alias_target=True), gen(2, retired_at=9_000.0), gen(3, readers=1),
                    gen(4, complete=False, retired_at=None, audit_reference=None)])
    assert out == {"1": "KEEP_ACTIVE", "2": "KEEP_RECENT", "3": "KEEP_READERS", "4": "KEEP_FAILED_EVIDENCE"}


def test_foreign_names_and_bad_inputs():
    foreign = GenerationFacts("other_alias__" + "0" * 32, ALIAS, False, True, True, 0, 0.0, "a")
    assert classify([gen(1, is_alias_target=True), foreign], now=1e4, grace_seconds=1)[1].verdict == "KEEP_UNCERTAIN"
    for bad in (dict(now=float("nan")), dict(grace_seconds=0), dict(grace_seconds=-1)):
        args = dict(now=1e4, grace_seconds=3600)
        args.update(bad)
        with pytest.raises(ValueError):
            classify([gen(1, is_alias_target=True)], **args)
    with pytest.raises(ValueError):
        classify([gen(1, is_alias_target=True), gen(1)], now=1e4, grace_seconds=1)


def test_the_module_cannot_delete_anything():
    import tests.claude_memory_eval.generation_retention as module
    from pathlib import Path
    source = Path(module.__file__).read_text(encoding="utf-8")
    assert "delete(" not in source and "drop" not in source.lower().replace("no delete/drop", "")
