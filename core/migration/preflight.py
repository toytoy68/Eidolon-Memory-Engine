"""Read-only structural preflight for legacy persistent Information files."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import yaml

from core.backend.errors import InvalidMemory
from core.backend.filesystem import FilesystemBackend
from core.information.models import (
    Confidence, EpistemicStatus, Importance, InformationType, OperationalState, Retention,
)
from core.migration.inventory import classify, symlink_ancestor
from core.persistence import has_symlink_component


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
    if not re.fullmatch(r"[A-Za-z0-9._-]+", path.stem):
        reasons.append("invalid_backend_id")
    revision = data.get("revision")
    if isinstance(revision, dict):
        if revision.keys() - {"number", "is_revision", "previous_revision"}:
            reasons.append("unknown_revision_fields")
        flag = revision.get("is_revision")
        if "is_revision" in revision and type(flag) is not bool:
            reasons.append("invalid_revision_flag")
        previous = revision.get("previous_revision")
        if previous is not None and (type(previous) is not int or previous < 1):
            reasons.append("invalid_previous_revision")
        number = revision.get("number")
        if (type(number) is int and number >= 1 and type(flag) is bool
                and (flag != (previous is not None)
                     or (type(previous) is int and previous >= number))):
            reasons.append("inconsistent_revision_history")
        revision = number
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


def inspect_core_information(path: Path) -> list[str]:
    """Verify a recognized core document can be read without creating directories."""
    try:
        memory = FilesystemBackend._deserialize(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, InvalidMemory, ValueError, TypeError):
        return ["invalid_core_information"]
    if (memory.information_id != path.stem
            or not re.fullmatch(r"[A-Za-z0-9._-]+", path.stem)
            or type(memory.revision) is not int or memory.revision < 1):
        return ["invalid_core_information"]
    return []


def preflight(engine_root: Path) -> dict:
    root = Path(engine_root)
    if has_symlink_component(root):
        raise ValueError("engine root contains a symlinked ancestor")
    if not root.is_dir():
        raise ValueError(f"engine root is not a directory: {root}")
    persistent = root / "memory" / "persistent"
    report = {"legacy_candidates": 0, "already_core": 0, "blocked": []}
    linked = symlink_ancestor(root, persistent)
    if linked is not None:
        report["blocked"].append({"path": linked.relative_to(root).as_posix(),
                                  "reasons": ["symlink_skipped"]})
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
            if reasons:
                report["blocked"].append({"path": relative, "reasons": reasons})
            else:
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
