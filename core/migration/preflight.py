"""Read-only structural preflight for legacy persistent Information files."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import yaml

from core.information.models import (
    Confidence, EpistemicStatus, Importance, InformationType, OperationalState, Retention,
)
from core.migration.inventory import classify


class UniqueKeyLoader(yaml.SafeLoader):
    """Reject ambiguous YAML mappings rather than silently choosing a key."""


def unique_mapping(loader, node):
    result = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=True)
        if not isinstance(key, str) or key in result:
            raise ValueError("duplicate or non-string YAML key")
        result[key] = loader.construct_object(value_node, deep=True)
    return result


UniqueKeyLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, unique_mapping)


def inspect_legacy_information(path: Path) -> list[str]:
    """Return reason codes only; never return metadata or document content."""
    if path.is_symlink():
        return ["symlink_skipped"]
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return ["unreadable"]
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].strip() != "---":
        return ["missing_front_matter"]
    end = next((i for i, line in enumerate(lines[1:], 1) if line.strip() == "---"), None)
    if end is None:
        return ["unclosed_front_matter"]
    try:
        data = yaml.load("".join(lines[1:end]), Loader=UniqueKeyLoader)
    except (yaml.YAMLError, ValueError):
        return ["invalid_or_ambiguous_yaml"]
    if not isinstance(data, dict):
        return ["invalid_mapping"]

    reasons = []
    known_fields = {
        "id", "revision", "type", "epistemic_status", "operational_state",
        "confidence", "importance", "context", "provenance", "evidence",
        "time", "relations", "triggers", "retention",
    }
    if data.keys() - known_fields:
        reasons.append("unknown_metadata_fields")
    if not isinstance(data.get("id"), str) or data["id"] != path.stem:
        reasons.append("identity_mismatch")
    revision = data.get("revision")
    if isinstance(revision, dict):
        if revision.keys() - {"number", "is_revision", "previous_revision"}:
            reasons.append("unknown_revision_fields")
        revision = revision.get("number")
    if type(revision) is not int or revision < 1:
        reasons.append("invalid_revision")
    enumerations = {
        "type": InformationType,
        "epistemic_status": EpistemicStatus,
        "operational_state": OperationalState,
        "confidence": Confidence,
        "importance": Importance,
        "retention": Retention,
    }
    for field, allowed in enumerations.items():
        value = data.get(field)
        if value is None:
            if field in {"type", "epistemic_status", "operational_state"}:
                reasons.append(f"missing_{field}")
        elif not isinstance(value, str) or value not in {item.value for item in allowed}:
            reasons.append(f"invalid_{field}")
    for field in ("context", "provenance", "evidence", "time"):
        if field in data and not isinstance(data[field], dict):
            reasons.append(f"invalid_{field}")
    for field in ("relations", "triggers"):
        if field in data and (not isinstance(data[field], list)
                              or any(not isinstance(item, dict) for item in data[field])):
            reasons.append(f"invalid_{field}")
    if not "".join(lines[end + 1:]).strip():
        reasons.append("empty_body")
    return reasons


def preflight(engine_root: Path) -> dict:
    root = Path(engine_root)
    if not root.is_dir():
        raise ValueError(f"engine root is not a directory: {root}")
    persistent = root / "memory" / "persistent"
    report = {"legacy_candidates": 0, "already_core": 0, "blocked": []}
    if persistent.is_symlink():
        report["blocked"].append({"path": "memory/persistent", "reasons": ["symlink_skipped"]})
        return report
    if not persistent.is_dir():
        return report
    for path in sorted(persistent.glob("*.md")):
        if not path.is_file() and not path.is_symlink():
            continue
        relative = path.relative_to(root).as_posix()
        kind = classify(path, "information")
        if kind in {"core_information_0.1", "core_information_0.2"}:
            report["already_core"] += 1
            continue
        if kind != "legacy_front_matter":
            report["blocked"].append({"path": relative, "reasons": [kind]})
            continue
        reasons = inspect_legacy_information(path)
        if reasons:
            report["blocked"].append({"path": relative, "reasons": reasons})
        else:
            report["legacy_candidates"] += 1
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Read-only legacy Information preflight")
    parser.add_argument("--root", type=Path, required=True, help="Engine root containing memory/")
    args = parser.parse_args(argv)
    try:
        report = preflight(args.root)
    except ValueError as exc:
        parser.error(str(exc))
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return int(bool(report["blocked"]))


if __name__ == "__main__":
    raise SystemExit(main())
