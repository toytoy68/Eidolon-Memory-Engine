# ==========================================================
# Projet      : Eidolon Memory Engine
# Organisation: Eidolon Core Technologies (ECT)
# Fichier     : core/migration/verification.py
# Description : Independent, read-only comparison of a legacy copy and its conversion.
# Standard    : Eidolon Presentation Standard v1
# ==========================================================

"""Independent, read-only comparison of a legacy copy and its conversion."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from core.backend.filesystem import FilesystemBackend
from core.migration.preflight import inspect_legacy_information
from core.migration.simulation import _candidate_issues, preview_legacy_information


def verify(source: Path, destination: Path) -> dict:
    """Check converted bytes and historical archives against the source copy.

    Rejected files remain decisions for a human. They cannot be counted as
    verified migrations, even when the rejection is correctly documented.
    """
    source, destination = Path(source).absolute(), Path(destination).absolute()
    report = json.loads((destination / "migration-report.json").read_text(encoding="utf-8"))
    issues: list[dict[str, str]] = []

    def issue(path: str, reason: str) -> None:
        issues.append({"file": path, "reason": reason})

    if report.get("source") != str(source) or report.get("destination") != str(destination):
        issue("migration-report.json", "wrong_source_or_destination")
    rejected = {item["file"] for item in report["rejected"]}
    seen: set[str] = set()
    accounted_output = {"migration-report.json", "memory/persistent/.write.lock"}
    converted = archived = 0
    persistent = source / "memory/persistent"
    for path in sorted(persistent.glob("*.md")):
        relative = path.relative_to(source).as_posix()
        seen.add(relative)
        accounted_output.add(f"memory/persistent/{path.name}")
        if path.is_symlink() or not path.is_file():
            if relative not in rejected:
                issue(relative, "unreported_rejection")
            continue
        reasons = inspect_legacy_information(path)
        if not reasons:
            reasons = _candidate_issues(path, persistent)
        if reasons:
            if relative not in rejected:
                issue(relative, "unreported_rejection")
            continue
        try:
            memory = preview_legacy_information(path)
            expected = FilesystemBackend._serialize_checked(memory).encode("utf-8")
        except (ValueError, TypeError, OSError):
            if relative not in rejected:
                issue(relative, "unreported_rejection")
            continue
        target = destination / "memory/persistent" / path.name
        if relative in rejected:
            if target.is_file() and not target.is_symlink() and target.read_bytes() == expected:
                issue(relative, "false_rejection")
            continue
        if target.is_symlink() or not target.is_file():
            issue(relative, "converted_file_missing")
        elif target.read_bytes() != expected:
            issue(relative, "converted_content_mismatch")
        else:
            converted += 1

    for path in sorted((source / "memory").rglob("*")):
        if path.is_dir() and not path.is_symlink():
            continue
        if path.parent == persistent and path.suffix == ".md":
            continue
        relative = path.relative_to(source).as_posix()
        seen.add(relative)
        accounted_output.add((Path("archive") / path.relative_to(source / "memory")).as_posix())
        if path.is_symlink() or not path.is_file():
            if relative not in rejected:
                issue(relative, "unreported_rejection")
            continue
        target = destination / "archive" / path.relative_to(source / "memory")
        if relative in rejected:
            if target.is_file() and not target.is_symlink() and target.read_bytes() == path.read_bytes():
                issue(relative, "false_rejection")
            continue
        if target.is_symlink() or not target.is_file():
            issue(relative, "archive_missing")
        elif target.read_bytes() != path.read_bytes():
            issue(relative, "archive_content_mismatch")
        else:
            archived += 1

    for relative in sorted(rejected - seen):
        issue(relative, "rejection_without_source")
    for path in sorted(destination.rglob("*")):
        if (path.is_file() or path.is_symlink()) and path.relative_to(destination).as_posix() not in accounted_output:
            issue(path.relative_to(destination).as_posix(), "unaccounted_output")
    if report.get("converted") != converted:
        issue("migration-report.json", "converted_count_mismatch")
    archive_count = sum(report.get(key, 0) for key in
                        ("archived_events", "archived_reviews", "archived_other"))
    if archive_count != archived:
        issue("migration-report.json", "archived_count_mismatch")
    return {"ok": not issues and not rejected, "checked_information": converted,
            "checked_archives": archived, "rejected": len(rejected),
            "issues": sorted(issues, key=lambda item: (item["file"], item["reason"]))}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--destination", type=Path, required=True)
    args = parser.parse_args(argv)
    result = verify(args.source, args.destination)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
