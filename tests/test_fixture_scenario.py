from hashlib import sha256
from pathlib import Path

from tools.generate_scenario import generate
from core.migration.preflight import preflight


def fingerprint(root: Path):
    return {path.relative_to(root).as_posix(): sha256(path.read_bytes()).hexdigest()
            for path in root.rglob("*") if path.is_file()}


def test_scenario_is_reproducible_and_has_realistic_shapes(tmp_path):
    first, second = tmp_path / "first", tmp_path / "second"
    counts = generate(first, seed=70427, count=500)
    assert generate(second, seed=70427, count=500) == counts
    assert fingerprint(first) == fingerprint(second)
    assert counts["information"] >= 498
    assert counts["threads"] >= 8
    assert counts["legacy_information"] == 500
    assert counts["pending_deletions"] >= 2
    assert counts["completed_deletions"] >= 1
    assert counts["refuted"] > 0 and counts["conflicted"] > 0
    assert preflight(first / "legacy")["legacy_candidates"] == 500


def test_scenario_refuses_to_overwrite_existing_output(tmp_path):
    from pytest import raises
    output = tmp_path / "existing"
    output.mkdir()
    (output / "important").write_text("keep")
    with raises(ValueError, match="empty"):
        generate(output, seed=1, count=500)
    assert (output / "important").read_text() == "keep"
