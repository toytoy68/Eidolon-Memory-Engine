import json

from core.migration.simulation import main, simulate, preview_legacy_information


def test_simulation_reports_mapping_and_legacy_data_without_writing(tmp_path, capsys):
    persistent = tmp_path / "memory/persistent"
    persistent.mkdir(parents=True)
    candidate = persistent / "info-1.md"
    candidate.write_text("---\nid: info-1\nrevision:\n  number: 2\n"
                         "type: FACT\nepistemic_status: UNVERIFIED\n"
                         "operational_state: ACTIVE\ncontext:\n  secret: private-value\n"
                         "---\n# Information\nsecret body\n")
    events = tmp_path / "memory/history/events"
    events.mkdir(parents=True)
    (events / "event-1.md").write_text("---\nevent_id: event-1\n---\nsecret event\n")
    reviews = tmp_path / "memory/history/reviews"
    reviews.mkdir(parents=True)
    (reviews / "review-1.md").write_text("---\nid: review-1\n---\nsecret review\n")
    before = {path: path.read_bytes() for path in tmp_path.rglob("*") if path.is_file()}

    assert main(["--root", str(tmp_path)]) == 0
    output = capsys.readouterr().out
    report = json.loads(output)
    assert report["information"]["candidates"] == ["memory/persistent/info-1.md"]
    assert report["other_data"]["events"] == {"legacy_front_matter": 1}
    assert report["other_data"]["reviews"] == {"legacy_front_matter": 1}
    assert report["field_mapping_proposal"]["revision.previous_revision"] == (
        "metadata.legacy_revision.previous_revision")
    assert "secret" not in output and "private-value" not in output
    assert {path: path.read_bytes() for path in tmp_path.rglob("*") if path.is_file()} == before
    assert not (persistent / ".write.lock").exists()
    assert simulate(tmp_path) == report


def test_simulation_blocks_ambiguous_or_non_json_metadata(tmp_path):
    persistent = tmp_path / "memory/persistent"
    persistent.mkdir(parents=True)
    (persistent / "date.md").write_text(
        "---\nid: date\nrevision: 1\ntype: FACT\n"
        "epistemic_status: UNVERIFIED\noperational_state: ACTIVE\n"
        "time:\n  created_at: 2026-09-29\n---\nbody\n")
    (persistent / "duplicate.md").write_text(
        "---\nid: duplicate\nid: other\nrevision: 1\n---\nbody\n")
    report = simulate(tmp_path)
    assert report["information"]["blocked"] == [
        {"path": "memory/persistent/date.md", "reasons": ["non_json_metadata_requires_policy"]},
        {"path": "memory/persistent/duplicate.md", "reasons": ["invalid_or_ambiguous_yaml"]},
    ]
    assert main(["--root", str(tmp_path)]) == 1


def test_preview_preserves_structured_revision_and_crlf_body(tmp_path):
    persistent = tmp_path / "memory/persistent"
    persistent.mkdir(parents=True)
    source = persistent / "info-2.md"
    source.write_bytes(
        b"---\r\nid: info-2\r\nrevision:\r\n  number: 3\r\n"
        b"  is_revision: true\r\n  previous_revision: 2\r\n"
        b"type: FACT\r\nepistemic_status: UNVERIFIED\r\n"
        b"operational_state: ACTIVE\r\nevidence:\r\n  supporting: []\r\n"
        b"relations: []\r\n---\r\n# Information\r\nsecret\r\n"
    )
    before = source.read_bytes()
    preview = preview_legacy_information(source)
    assert preview.revision == 3
    assert preview.metadata["legacy_revision"] == {
        "shape": "structured", "is_revision": True, "previous_revision": 2,
    }
    assert preview.verification == {"evidence": {"supporting": []}}
    assert preview.content == "# Information\r\nsecret\r\n"
    assert simulate(tmp_path)["information"]["candidates"] == ["memory/persistent/info-2.md"]
    assert source.read_bytes() == before
