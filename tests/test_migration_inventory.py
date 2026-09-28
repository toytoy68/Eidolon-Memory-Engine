import json

from core.migration.inventory import inventory, main


def write(root, relative, content):
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def test_inventory_classifies_both_generations_without_changing_files(tmp_path):
    old = write(tmp_path, "memory/persistent/old.md", "---\nid: old\n---\nSecret content\n")
    new = write(tmp_path, "memory/persistent/new.md",
                '# Eidolon Information Object\n\nVersion: 0.2\n\n```json\n{}\n```\n')
    write(tmp_path, "memory/persistent/threads/thread.md",
          '# Eidolon Thread Object\n\nVersion: 0.1\n')
    write(tmp_path, "memory/history/events/event.md", "event_id: legacy\n")
    write(tmp_path, "memory/history/operations/old.json",
          json.dumps({"operation_id": "old", "result": "STORE"}))
    write(tmp_path, "memory/history/operations/thread-status-v1/new.json",
          json.dumps({"operation_type": "THREAD_STATUS_CHANGE"}))
    write(tmp_path, "memory/history/operations/thread-create-v1/created.json",
          json.dumps({"operation_type": "THREAD_CREATE"}))
    write(tmp_path, "memory/history/events/thread-create-v1/created.md",
          '# Eidolon Memory Event\n\nVersion: 0.2\n')
    write(tmp_path, "memory/history/events/broken.md", "unexpected\n")

    report = inventory(tmp_path)

    assert report["categories"]["information"] == {
        "legacy_front_matter": 1, "core_information_0.2": 1,
    }
    assert report["categories"]["threads"] == {"core_thread_0.1": 1}
    assert report["categories"]["events"] == {"legacy_event_plain": 1, "unknown": 1}
    assert report["categories"]["operations"] == {"legacy_operation": 1}
    assert report["categories"]["thread_status_operations"] == {"core_operation": 1}
    assert report["categories"]["thread_create_operations"] == {"core_operation": 1}
    assert report["categories"]["thread_create_events"] == {"core_event_0.2": 1}
    assert report["needs_review"] == [
        {"path": "memory/history/events/broken.md", "reason": "unknown"},
    ]
    assert old.read_text() == "---\nid: old\n---\nSecret content\n"
    assert new.exists()
    assert not (tmp_path / "memory/history/operations/.write.lock").exists()
    assert "Secret content" not in json.dumps(report)


def test_inventory_skips_symlinks_and_reports_bad_json(tmp_path):
    outside = write(tmp_path, "outside.md", "confidential")
    events = tmp_path / "memory/history/events"
    events.mkdir(parents=True)
    (events / "linked.md").symlink_to(outside)
    write(tmp_path, "memory/history/operations/bad.json", "{not-json")

    report = inventory(tmp_path)
    assert {entry["reason"] for entry in report["needs_review"]} == {
        "symlink_skipped", "unreadable_or_invalid",
    }


def test_cli_reports_inventory_without_content(tmp_path, capsys):
    write(tmp_path, "memory/working/item.md", "---\nid: i\n---\nprivate\n")
    assert main(["--root", str(tmp_path)]) == 0
    output = capsys.readouterr().out
    assert json.loads(output)["categories"]["working"] == {"legacy_front_matter": 1}
    assert "private" not in output
