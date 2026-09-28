import json

from core.migration.preflight import main, preflight


def document(root, name, front_matter, body="\n# Information\nprivate content\n"):
    path = root / "memory" / "persistent" / f"{name}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("---\n" + front_matter + "---\n" + body, encoding="utf-8")
    return path


def test_preflight_reports_candidates_and_blocks_without_modifying_data(tmp_path, capsys):
    good = document(tmp_path, "info-1",
                    "id: info-1\nrevision:\n  number: 2\ntype: FACT\n"
                    "epistemic_status: UNVERIFIED\noperational_state: ACTIVE\n")
    document(tmp_path, "info-2",
             "id: info-2\nid: another\nrevision: 1\ntype: FACT\n"
             "epistemic_status: UNVERIFIED\noperational_state: ACTIVE\n")
    document(tmp_path, "info-3",
             "id: wrong\nrevision: true\ntype: FACT\n"
             "epistemic_status: UNVERIFIED\noperational_state: ACTIVE\n")
    before = good.read_bytes()

    assert main(["--root", str(tmp_path)]) == 1
    report = json.loads(capsys.readouterr().out)
    assert report["legacy_candidates"] == 1
    assert report["blocked"] == [
        {"path": "memory/persistent/info-2.md", "reasons": ["invalid_or_ambiguous_yaml"]},
        {"path": "memory/persistent/info-3.md",
         "reasons": ["identity_mismatch", "invalid_revision"]},
    ]
    assert good.read_bytes() == before
    assert "private content" not in json.dumps(report)
    assert not (good.parent / ".write.lock").exists()


def test_preflight_skips_core_and_rejects_empty_body(tmp_path):
    document(tmp_path, "empty", "id: empty\nrevision: 1\ntype: FACT\n"
             "epistemic_status: UNVERIFIED\noperational_state: ACTIVE\n", body="\n")
    core = tmp_path / "memory/persistent/core.md"
    core.write_text("# Eidolon Information Object\n\nVersion: 0.2\n", encoding="utf-8")
    report = preflight(tmp_path)
    assert report["already_core"] == 1
    assert report["blocked"] == [
        {"path": "memory/persistent/empty.md", "reasons": ["empty_body"]},
    ]
