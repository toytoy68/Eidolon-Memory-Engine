from hashlib import sha256
from pathlib import Path

from core.backend.filesystem import FilesystemBackend
from core.migration.converter import convert
from tools.generate_scenario import generate


def fingerprints(root: Path):
    return {path.relative_to(root).as_posix(): sha256(path.read_bytes()).hexdigest()
            for path in root.rglob("*") if path.is_file()}


def test_converter_is_idempotent_and_preserves_historical_files(tmp_path):
    fixture = tmp_path / "fixture"
    generate(fixture, count=50)
    source = fixture / "legacy"
    original = fingerprints(source)
    destination = tmp_path / "converted"

    first = convert(source, destination)
    after_first = fingerprints(destination)
    second = convert(source, destination)

    assert first["converted"] == 50
    assert first["archived_events"] == first["archived_reviews"] == 6
    assert first["rejected"] == []
    assert second == first
    assert fingerprints(destination) == after_first
    assert fingerprints(source) == original
    assert FilesystemBackend._deserialize(
        (destination / "memory/persistent/info-fixture-0000.md").read_text()).information_id == "info-fixture-0000"
    assert (destination / "archive/history/events/event-00.md").read_bytes() == (
        source / "memory/history/events/event-00.md").read_bytes()


def test_converter_reports_corrupt_source_and_destination_conflict(tmp_path):
    source = tmp_path / "source"
    (source / "memory/persistent").mkdir(parents=True)
    (source / "memory/persistent/broken.md").write_text("---\nid: broken\n")
    fixture = tmp_path / "fixture"
    generate(fixture, count=50)
    valid = fixture / "legacy/memory/persistent/info-fixture-0000.md"
    (source / "memory/persistent/info-fixture-0000.md").write_bytes(valid.read_bytes())
    destination = tmp_path / "converted"

    report = convert(source, destination)
    assert report["converted"] == 1
    assert any(item["file"].endswith("broken.md") and item["reason"]
               and item["action_suggested"] for item in report["rejected"])
    written = destination / "memory/persistent/info-fixture-0000.md"
    written.write_text("other data")
    rerun = convert(source, destination)
    assert any(item["reason"] == "destination_conflict" for item in rerun["rejected"])
    assert written.read_text() == "other data"


def test_converter_explicitly_rejects_unsafe_historical_event(tmp_path):
    source = tmp_path / "source"
    (source / "memory/persistent").mkdir(parents=True)
    events = source / "memory/history/events"
    events.mkdir(parents=True)
    outside = tmp_path / "private"
    outside.write_text("must not copy")
    (events / "linked.md").symlink_to(outside)

    report = convert(source, tmp_path / "dest")

    assert report["archived_events"] == 0
    assert report["rejected"] == [{
        "file": "memory/history/events/linked.md", "reason": "unsafe_archive_path",
        "action_suggested": "Review and copy manually after resolving the link",
    }]
    assert not (tmp_path / "dest/archive/history/events/linked.md").exists()


def test_converter_does_not_follow_linked_source_tree(tmp_path):
    import pytest
    outside = tmp_path / "outside"
    (outside / "persistent").mkdir(parents=True)
    source = tmp_path / "source"
    source.mkdir()
    (source / "memory").symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValueError, match="symlinked"):
        convert(source, tmp_path / "destination")
    assert not (tmp_path / "destination").exists()


def test_converter_keeps_authored_revision_relation_and_epistemic_status(tmp_path):
    fixture = tmp_path / "fixture"
    generate(fixture, count=60)
    source, destination = fixture / "legacy", tmp_path / "converted"

    report = convert(source, destination)

    assert report["rejected"] == []
    root = destination / "memory/persistent"
    structured = FilesystemBackend._deserialize((root / "info-fixture-0000.md").read_text())
    related = FilesystemBackend._deserialize((root / "info-fixture-0005.md").read_text())
    refuted = FilesystemBackend._deserialize((root / "info-fixture-0020.md").read_text())
    conflicted = FilesystemBackend._deserialize((root / "info-fixture-0030.md").read_text())
    assert structured.revision == 1
    assert structured.metadata["legacy_revision"] == {
        "shape": "structured", "is_revision": False}
    assert related.relations == [{"type": "RELATED_TO", "target_id": "info-fixture-0004"}]
    assert refuted.metadata["epistemic_status"] == "REFUTED"
    assert conflicted.metadata["epistemic_status"] == "CONFLICTED"
    assert related.verification == {"evidence": {"supporting": ["sample-00"]}}
    assert structured.content.startswith("Observation anonyme info-fixture-0000")
