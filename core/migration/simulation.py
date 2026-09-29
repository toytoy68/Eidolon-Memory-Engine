"""Read-only migration feasibility report; never create converted documents."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import yaml

from core.migration.inventory import inventory, classify
from core.migration.preflight import UniqueKeyLoader, inspect_core_information, inspect_legacy_information


# Proposed mapping only. No writer consumes it until the target contract is approved.
FIELD_MAPPING = {
    "id": "information_id",
    "revision": "revision (number if structured)",
    "body": "content (exact bytes after closing front matter, pending policy)",
    "type": "metadata.type",
    "epistemic_status": "metadata.epistemic_status",
    "operational_state": "metadata.operational_state",
    "confidence": "metadata.confidence",
    "importance": "metadata.importance",
    "context": "metadata.context",
    "provenance": "provenance",
    "evidence": "verification.evidence",
    "time": "temporal",
    "relations": "relations",
    "triggers": "metadata.triggers",
    "retention": "metadata.retention",
    "revision.is_revision": "metadata.legacy_revision.is_revision",
    "revision.previous_revision": "metadata.legacy_revision.previous_revision",
}


def _candidate_issues(path: Path) -> list[str]:
    """Check the proposed JSON target without exposing any source values."""
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines(keepends=True)
    end = next(i for i, line in enumerate(lines[1:], 1) if line.strip() == "---")
    data = yaml.load("".join(lines[1:end]), Loader=UniqueKeyLoader)
    try:
        json.dumps(data, ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError, OverflowError):
        return ["non_json_metadata_requires_policy"]
    return []


def simulate(engine_root: Path) -> dict:
    root = Path(engine_root)
    source_inventory = inventory(root)
    persistent = root / "memory/persistent"
    report = {
        "field_mapping_proposal": FIELD_MAPPING,
        "information": {"candidates": [], "already_core": [], "blocked": []},
        "other_data": {
            "events": source_inventory["categories"]["events"],
            "reviews": source_inventory["categories"]["reviews"],
            "operations": source_inventory["categories"]["operations"],
            "policy": "archive_or_convert_requires_decision",
        },
        "inventory_needs_review": source_inventory["needs_review"],
    }
    if persistent.is_symlink():
        report["information"]["blocked"].append(
            {"path": "memory/persistent", "reasons": ["symlink_skipped"]})
        return report
    if not persistent.is_dir():
        return report
    for path in sorted(persistent.glob("*.md")):
        if not path.is_file() and not path.is_symlink():
            continue
        relative = path.relative_to(root).as_posix()
        kind = classify(path, "information")
        if kind in {"core_information_0.1", "core_information_0.2"}:
            reasons = inspect_core_information(path)
            destination = "already_core"
        elif kind == "legacy_front_matter":
            reasons = inspect_legacy_information(path)
            if not reasons:
                reasons = _candidate_issues(path)
            destination = "candidates"
        else:
            reasons = [kind]
            destination = "blocked"
        if reasons:
            report["information"]["blocked"].append({"path": relative, "reasons": reasons})
        else:
            report["information"][destination].append(relative)
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Read-only Information migration simulation")
    parser.add_argument("--root", type=Path, required=True, help="Copy of engine root containing memory/")
    args = parser.parse_args(argv)
    try:
        report = simulate(args.root)
    except ValueError as exc:
        parser.error(str(exc))
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return int(bool(report["information"]["blocked"] or report["inventory_needs_review"]))


if __name__ == "__main__":
    raise SystemExit(main())
