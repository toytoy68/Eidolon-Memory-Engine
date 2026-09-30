"""A converted copy can be checked without trusting the converter's counters."""

from hashlib import sha256

from core.migration.converter import convert
from core.migration.verification import verify
from tools.generate_scenario import generate


def snapshot(root):
    return {str(path.relative_to(root)): sha256(path.read_bytes()).hexdigest()
            for path in root.rglob("*") if path.is_file()}


def test_verification_checks_documents_archives_and_is_read_only(tmp_path):
    generate(tmp_path / "fixture", count=50)
    source = tmp_path / "fixture/legacy"
    destination = tmp_path / "converted"
    convert(source, destination)
    before_source, before_destination = snapshot(source), snapshot(destination)

    report = verify(source, destination)

    assert report["ok"] is True
    assert report["checked_information"] == 50
    assert report["checked_archives"] == 15
    assert report["issues"] == []
    assert snapshot(source) == before_source
    assert snapshot(destination) == before_destination


def test_verification_detects_tampered_converted_information(tmp_path):
    generate(tmp_path / "fixture", count=50)
    source = tmp_path / "fixture/legacy"
    destination = tmp_path / "converted"
    convert(source, destination)
    path = destination / "memory/persistent/info-fixture-0000.md"
    path.write_bytes(path.read_bytes() + b"changed")

    report = verify(source, destination)

    assert report["ok"] is False
    assert any(issue["reason"] == "converted_content_mismatch" and
               issue["file"] == "memory/persistent/info-fixture-0000.md"
               for issue in report["issues"])


def test_verification_detects_lost_historical_review_and_false_reject(tmp_path):
    generate(tmp_path / "fixture", count=50)
    source = tmp_path / "fixture/legacy"
    destination = tmp_path / "converted"
    convert(source, destination)
    (destination / "archive/history/reviews/review-00.md").unlink()
    report_file = destination / "migration-report.json"
    import json
    report = json.loads(report_file.read_text())
    report["rejected"].append({"file": "memory/persistent/info-fixture-0001.md",
                               "reason": "invented", "action_suggested": "none"})
    report_file.write_text(json.dumps(report))

    result = verify(source, destination)

    assert result["ok"] is False
    assert {item["reason"] for item in result["issues"]} >= {
        "archive_missing", "false_rejection",
    }


def test_verification_detects_unaccounted_output(tmp_path):
    generate(tmp_path / "fixture", count=50)
    source = tmp_path / "fixture/legacy"
    destination = tmp_path / "converted"
    convert(source, destination)
    (destination / "archive/history/events/unaccounted.md").write_text("extra")

    result = verify(source, destination)

    assert {"file": "archive/history/events/unaccounted.md",
            "reason": "unaccounted_output"} in result["issues"]
