#!/usr/bin/env python3

import argparse
import re
import sys
from pathlib import Path

ENGINE_ROOT = Path(
    __file__
).resolve().parents[2]

sys.path.insert(
    0,
    str(ENGINE_ROOT)
)

from core.config import (
    SCHEMAS_ROOT,
)

SCHEMAS = SCHEMAS_ROOT

EPISTEMIC = {
    "UNKNOWN", "UNVERIFIED", "CONFIRMED",
    "REFUTED", "CONFLICTED", "SUPERSEDED",
}

OPERATIONAL = {
    "ACTIVE", "PLANNED", "PENDING_REVIEW",
    "CANCELLED", "COMPLETED", "DEPRECATED",
}

RELATIONS = {
    "SUPPORTS", "CONTRADICTS", "DERIVED_FROM", "DEPENDS_ON",
    "SUPERSEDES", "RELATED_TO", "PART_OF", "INSTANCE_OF",
    "CAUSED_BY", "FOLLOWS",
}

SOURCE_TYPES = {
    "USER_STATEMENT", "SYSTEM_GENERATED", "DIRECT_OBSERVATION",
    "MEASUREMENT", "EXPERIMENT", "DOCUMENTATION",
    "EXTERNAL_SOURCE", "TOOL_OUTPUT", "MODEL_OUTPUT",
    "IMPORTED_DATA",
}

TIME_FIELDS = (
    "created_at", "observed_at", "verified_at",
    "updated_at", "valid_from", "valid_until",
)


def parse_front_matter(text):
    lines = text.splitlines()
    data = {}

    for line in lines:
        if line.startswith("# "):
            break
        match = re.match(r"^([A-Za-z0-9_]+):\s*(.*)$", line)
        if match:
            data[match.group(1)] = match.group(2).strip().strip('"')

    return data


def validate_file(path):
    errors = []
    warnings = []

    if not path.is_file():
        return [f"fichier introuvable: {path}"], []

    text = path.read_text(encoding="utf-8")
    data = parse_front_matter(text)

    required = (
        "id", "revision", "type", "epistemic_status",
        "operational_state", "confidence", "importance",
    )

    for key in required:
        if key not in data:
            errors.append(f"champ absent: {key}")

    if data.get("epistemic_status") not in EPISTEMIC:
        if "epistemic_status" in data:
            errors.append(
                f"epistemic_status invalide: {data['epistemic_status']}"
            )

    if data.get("operational_state") not in OPERATIONAL:
        if "operational_state" in data:
            errors.append(
                f"operational_state invalide: {data['operational_state']}"
            )

    if "provenance:" not in text:
        errors.append("bloc provenance absent")

    if "relations:" not in text:
        errors.append("bloc relations absent")

    if "time:" not in text:
        warnings.append("bloc time absent")

    for field in TIME_FIELDS:
        if re.search(rf"^{re.escape(field)}:\s*$", text, re.MULTILINE):
            warnings.append(f"{field} présent mais non renseigné")

    relation_block = re.search(
        r"^relations:\s*\n(.*?)(?=^\S|\Z)",
        text,
        re.MULTILINE | re.DOTALL,
    )

    if relation_block:
        for rel in re.findall(r"type:\s*([A-Z_]+)", relation_block.group(1)):
            if rel not in RELATIONS:
                errors.append(f"relation invalide: {rel}")

    source_match = re.search(r"source_type:\s*([A-Z_]+)", text)
    if source_match and source_match.group(1) not in SOURCE_TYPES:
        errors.append(f"source_type invalide: {source_match.group(1)}")

    return errors, warnings


def command_validate(path):
    errors, warnings = validate_file(path)

    print(f"Fichier : {path}")

    if warnings:
        print("Avertissements :")
        for warning in warnings:
            print(f"- {warning}")

    if errors:
        print("Validation sémantique : ERREUR")
        for error in errors:
            print(f"- {error}")
        return 1

    print("Validation sémantique : OK")
    return 0


def command_schemas():
    required = [
        "information.md",
        "memory-relation.md",
        "memory-provenance.md",
        "memory-temporal.md",
        "memory-verification.md",
    ]

    failed = False

    for name in required:
        path = SCHEMAS / name
        if path.is_file() and path.stat().st_size > 0:
            print(f"OK : {path}")
        else:
            print(f"ERREUR : {path}")
            failed = True

    return 1 if failed else 0


parser = argparse.ArgumentParser(
    description="Eidolon Memory Semantic Validator"
)
sub = parser.add_subparsers(dest="command", required=True)

validate = sub.add_parser("validate")
validate.add_argument("information")

sub.add_parser("schemas")

args = parser.parse_args()

if args.command == "validate":
    sys.exit(command_validate(Path(args.information)))

if args.command == "schemas":
    sys.exit(command_schemas())
