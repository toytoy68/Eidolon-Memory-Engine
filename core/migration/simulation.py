"""Read-only migration feasibility report; never create converted documents."""

from __future__ import annotations

import argparse
from collections import Counter
import json
import re
from pathlib import Path

import yaml

from core.backend.filesystem import FilesystemBackend
from core.backend.models import Memory
from core.events.models import EventType
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

RELATION_TYPES = {
    "SUPPORTS", "CONTRADICTS", "DERIVED_FROM", "DEPENDS_ON", "SUPERSEDES",
    "RELATED_TO", "PART_OF", "INSTANCE_OF", "CAUSED_BY", "FOLLOWS",
}


def _history_summary(root: Path, category: str, field: str, allowed: set[str]) -> tuple[dict, list]:
    directory = root / "memory/history" / category
    counts: Counter[str] = Counter()
    issues = []
    if directory.is_symlink():
        return {}, [{"path": f"memory/history/{category}", "reason": "symlink_skipped"}]
    if not directory.is_dir():
        return {}, []
    for path in sorted(directory.glob("*.md")):
        relative = path.relative_to(root).as_posix()
        kind = classify(path, category)
        if kind == "core_event_0.2" and category == "events":
            counts["core_event_0.2"] += 1
            continue
        if kind != "legacy_front_matter" and not (category == "events" and kind == "legacy_event_plain"):
            issues.append({"path": relative, "reason": "unrecognized_history_format"})
            continue
        try:
            with path.open("r", encoding="utf-8") as handle:
                header = handle.read(65536)
            if kind == "legacy_front_matter":
                lines = header.splitlines(keepends=True)
                end = next(i for i, line in enumerate(lines[1:], 1) if line.strip() == "---")
                record = yaml.load("".join(lines[1:end]), Loader=UniqueKeyLoader)
                value = record.get(field) if isinstance(record, dict) else None
                reference = record.get("information_id") if isinstance(record, dict) else None
            else:
                plain_header = header.split("\n---", 1)[0]
                match = re.search(rf"(?m)^{re.escape(field)}:\s*([A-Z_]+)\s*$", plain_header)
                value = match.group(1) if match else None
                reference_match = re.search(r"(?m)^information_id:\s*([A-Za-z0-9._-]+)\s*$", plain_header)
                reference = reference_match.group(1) if reference_match else None
        except (OSError, UnicodeError, ValueError, StopIteration, yaml.YAMLError):
            value = None
            reference = None
        if not isinstance(value, str) or value not in allowed:
            issues.append({"path": relative, "reason": "unrecognized_history_value"})
        else:
            counts[value] += 1
        if not isinstance(reference, str) or not re.fullmatch(r"[A-Za-z0-9._-]+", reference):
            issues.append({"path": relative, "reason": "invalid_history_reference"})
        else:
            targets = []
            unsafe = False
            for directory in (root / "memory/working", root / "memory/persistent"):
                candidate = directory / f"{reference}.md"
                if directory.is_symlink() or candidate.is_symlink():
                    if candidate.exists() or candidate.is_symlink():
                        unsafe = True
                    continue
                if candidate.is_file():
                    targets.append(candidate)
            if unsafe:
                issues.append({"path": relative, "reason": "unsafe_history_reference"})
            elif not targets:
                issues.append({"path": relative, "reason": "unresolved_history_reference"})
            elif len(targets) > 1:
                issues.append({"path": relative, "reason": "ambiguous_history_reference"})
            else:
                target = targets[0]
                target_kind = classify(target, "information")
                if target_kind in {"core_information_0.1", "core_information_0.2"}:
                    reasons = inspect_core_information(target)
                elif target_kind == "legacy_front_matter":
                    reasons = inspect_legacy_information(target)
                else:
                    reasons = [target_kind]
                if reasons:
                    issues.append({"path": relative, "reason": "invalid_history_reference"})
    return dict(sorted(counts.items())), issues


def preview_legacy_information(path: Path) -> Memory:
    """Build a proposed core object in memory; callers must preflight first."""
    # read_text() translates CRLF on some platforms, so decode the raw bytes.
    text = path.read_bytes().decode("utf-8")
    lines = text.splitlines(keepends=True)
    end = next(i for i, line in enumerate(lines[1:], 1) if line.strip() == "---")
    data = yaml.load("".join(lines[1:end]), Loader=UniqueKeyLoader)
    revision = data["revision"]
    metadata = {key: data[key] for key in (
        "type", "epistemic_status", "operational_state", "confidence",
        "importance", "context", "triggers", "retention",
    ) if key in data}
    if isinstance(revision, dict):
        metadata["legacy_revision"] = {
            "shape": "structured",
            **{key: revision[key] for key in ("is_revision", "previous_revision")
               if key in revision},
        }
        revision = revision["number"]
    return Memory(
        information_id=data["id"], revision=revision,
        content="".join(lines[end + 1:]), metadata=metadata,
        provenance=data.get("provenance", {}),
        temporal=data.get("time", {}),
        verification={"evidence": data["evidence"]} if "evidence" in data else {},
        relations=data.get("relations", []),
    )


def _candidate_issues(path: Path, persistent: Path) -> list[str]:
    """Test an in-memory projection without exposing any source values."""
    try:
        projected = preview_legacy_information(path)
        encoded = FilesystemBackend._serialize(projected)
        if FilesystemBackend._deserialize(encoded) != projected:
            return ["core_round_trip_mismatch"]
    except (TypeError, ValueError, OverflowError):
        return ["non_json_metadata_requires_policy"]
    reasons = []
    for relation in projected.relations:
        relation_type = relation.get("type")
        if relation_type == "RELATES_TO" and "legacy_relation_alias_requires_policy" not in reasons:
            reasons.append("legacy_relation_alias_requires_policy")
        elif not isinstance(relation_type, str) or relation_type not in RELATION_TYPES:
            if "unknown_relation_type" not in reasons:
                reasons.append("unknown_relation_type")
        target_id = relation.get("target_id")
        legacy_target = relation.get("target")
        if target_id is not None and legacy_target is not None and target_id != legacy_target:
            reason = "ambiguous_relation_target"
        else:
            target = target_id if target_id is not None else legacy_target
            if not isinstance(target, str) or not re.fullmatch(r"[A-Za-z0-9._-]+", target):
                reason = "invalid_relation_target"
            else:
                linked = persistent / f"{target}.md"
                if linked.is_symlink() or not linked.is_file():
                    reason = "unresolved_relation_target"
                else:
                    reason = None
        if reason and reason not in reasons:
            reasons.append(reason)
    # An older relations CLI could append a textual relation in the Markdown
    # body instead of the front matter. Preserve it, but require human mapping.
    if re.search(r"(?m)^\s*-\s*type:\s*[^\n]+\n\s*target:\s*[^\n]+", projected.content):
        reasons.append("body_relation_requires_policy")
    return reasons


def simulate(engine_root: Path) -> dict:
    root = Path(engine_root)
    source_inventory = inventory(root)
    event_types, event_issues = _history_summary(
        root, "events", "event_type", {item.value for item in EventType} | {"STORED", "RELATION_ADDED"})
    review_statuses, review_issues = _history_summary(
        root, "reviews", "status", {"PENDING_REVIEW", "RESOLVED"})
    persistent = root / "memory/persistent"
    report = {
        "field_mapping_proposal": FIELD_MAPPING,
        "information": {"candidates": [], "already_core": [], "blocked": []},
        "other_data": {
            "events": source_inventory["categories"]["events"],
            "reviews": source_inventory["categories"]["reviews"],
            "operations": source_inventory["categories"]["operations"],
            "event_types": event_types,
            "review_statuses": review_statuses,
            "requires_policy": {
                "events": {key: event_types[key] for key in ("STORED", "RELATION_ADDED")
                           if key in event_types},
                "reviews": review_statuses,
            },
            "policy": "archive_or_convert_requires_decision",
        },
        "inventory_needs_review": source_inventory["needs_review"] + event_issues + review_issues,
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
                reasons = _candidate_issues(path, persistent)
            destination = "candidates"
        else:
            reasons = [kind]
            destination = "blocked"
        if reasons:
            report["information"]["blocked"].append({"path": relative, "reasons": reasons})
        else:
            report["information"][destination].append(relative)
    # A candidate depending on a blocked Information cannot be considered
    # ready either. Repeat to cover chains of relations without exposing IDs.
    information = report["information"]
    while True:
        blocked_ids = {Path(item["path"]).stem for item in information["blocked"]}
        dependent = []
        for relative in information["candidates"]:
            preview = preview_legacy_information(root / relative)
            if any((relation.get("target_id") or relation.get("target")) in blocked_ids
                   for relation in preview.relations):
                dependent.append(relative)
        if not dependent:
            break
        information["candidates"] = [path for path in information["candidates"]
                                     if path not in dependent]
        information["blocked"].extend(
            {"path": path, "reasons": ["relation_target_blocked"]} for path in dependent)
        information["blocked"].sort(key=lambda item: item["path"])
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
