#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys

ALLOWED_MECHANISMS = (
    "WORKING",
    "EPISODIC",
    "SEMANTIC",
    "ASSOCIATIVE",
    "PROCEDURAL",
    "PROSPECTIVE",
)


def parse_front_matter(text: str) -> dict[str, str]:
    if not text.startswith("---\n"):
        raise ValueError("front matter absent")

    parts = text.split("---\n", 2)

    if len(parts) < 3:
        raise ValueError("front matter incomplet")

    front = parts[1]
    fields: dict[str, str] = {}

    for line in front.splitlines():
        match = re.match(r"^([A-Za-z0-9_]+):\s*(.*)$", line)

        if match:
            key, value = match.groups()
            fields[key] = value.strip()

    return fields


def classify(
    fields: dict[str, str],
    text: str,
) -> dict[str, tuple[str, str]]:

    result: dict[str, tuple[str, str]] = {}

    info_type = fields.get("type", "").upper()
    epistemic = fields.get("epistemic_status", "").upper()

    # WORKING
    result["WORKING"] = (
        "YES",
        "Information analysée depuis Working Memory.",
    )

    # EPISODIC
    episodic_types = {
        "OBSERVATION",
        "EVENT",
        "MEASUREMENT",
        "DECISION",
    }

    if info_type in episodic_types:
        result["EPISODIC"] = (
            "YES",
            f"type {info_type} compatible avec une expérience ou un événement.",
        )
    else:
        result["EPISODIC"] = (
            "POSSIBLE",
            "Le type ne permet pas de confirmer seul un caractère épisodique.",
        )

    # SEMANTIC
    semantic_types = {
        "FACT",
        "CONCEPT",
        "OBSERVATION",
        "PROCEDURE",
    }

    if info_type in semantic_types and epistemic == "CONFIRMED":
        result["SEMANTIC"] = (
            "POSSIBLE",
            "Information confirmée pouvant contribuer à une connaissance réutilisable.",
        )
    elif info_type in semantic_types:
        result["SEMANTIC"] = (
            "POSSIBLE",
            "Type compatible avec Semantic Memory mais état épistémique non confirmé.",
        )
    else:
        result["SEMANTIC"] = (
            "POSSIBLE",
            "Classification sémantique non déterminable uniquement par le type.",
        )

    # ASSOCIATIVE
    if re.search(
        r"(^|\n)\s*-\s*type:\s*(SUPPORTS|CONTRADICTS|DERIVED_FROM|"
        r"DEPENDS_ON|SUPERSEDES|REQUIRES|CONCERNS)\b",
        text,
        flags=re.IGNORECASE,
    ):
        result["ASSOCIATIVE"] = (
            "YES",
            "Une relation mémoire explicite est présente.",
        )
    else:
        result["ASSOCIATIVE"] = (
            "POSSIBLE",
            "Une association peut exister mais aucune relation explicite n'a été détectée.",
        )

    # PROCEDURAL
    if info_type == "PROCEDURE":
        result["PROCEDURAL"] = (
            "YES",
            "Type PROCEDURE détecté.",
        )
    else:
        result["PROCEDURAL"] = (
            "NO",
            "Aucun type PROCEDURE détecté.",
        )

    # PROSPECTIVE
    #
    # Version 21.1 :
    # aucune détection heuristique de trigger dans le texte.
    # Les champs prospectifs structurés ne sont pas encore définis
    # par le classificateur.
    result["PROSPECTIVE"] = (
        "NO",
        "Aucun mécanisme prospectif structuré détecté.",
    )

    return result


def build_machine_result(
    fields: dict[str, str],
    result: dict[str, tuple[str, str]],
) -> dict:

    classification = {}

    for mechanism in ALLOWED_MECHANISMS:
        status, reason = result[mechanism]

        classification[mechanism] = {
            "status": status,
            "reason": reason,
        }

    return {
        "classifier": {
            "component": "memory-mechanism-classifier",
            "version": "21.1",
        },
        "information": {
            "id": fields.get("id"),
            "revision": fields.get("revision"),
            "type": fields.get("type"),
            "epistemic_status": fields.get(
                "epistemic_status",
                "UNKNOWN",
            ),
            "operational_state": fields.get(
                "operational_state",
                "UNKNOWN",
            ),
        },
        "classification": classification,
    }


def validate_path(
    path: Path,
    json_output: bool = False,
) -> int:

    if not path.is_file():
        print(
            f"ERREUR : Information introuvable : {path}",
            file=sys.stderr,
        )
        return 1

    try:
        text = path.read_text(encoding="utf-8")
        fields = parse_front_matter(text)
    except (OSError, ValueError) as exc:
        print(
            f"ERREUR : lecture impossible : {exc}",
            file=sys.stderr,
        )
        return 1

    if "id" not in fields:
        print("ERREUR : champ id absent.", file=sys.stderr)
        return 1

    if "type" not in fields:
        print("ERREUR : champ type absent.", file=sys.stderr)
        return 1

    result = classify(fields, text)

    if json_output:
        machine_result = build_machine_result(
            fields,
            result,
        )

        print(
            json.dumps(
                machine_result,
                ensure_ascii=False,
                indent=2,
            )
        )

        return 0

    print(f"Information : {fields['id']}")
    print(f"Type       : {fields['type']}")
    print(
        f"Epistemic  : "
        f"{fields.get('epistemic_status', 'UNKNOWN')}"
    )
    print()
    print("Classification mémoire :")
    print()

    for mechanism in ALLOWED_MECHANISMS:
        status, reason = result[mechanism]

        print(f"{mechanism:<12} : {status}")
        print(f"  -> {reason}")

    print()
    print("Aucune modification effectuée.")

    return 0


def main() -> int:

    parser = argparse.ArgumentParser(
        description="Eidolon Memory Mechanism Classifier"
    )

    sub = parser.add_subparsers(
        dest="command",
        required=True,
    )

    classify_parser = sub.add_parser("classify")

    classify_parser.add_argument(
        "--json",
        action="store_true",
        help="Produce structured machine-readable output.",
    )

    classify_parser.add_argument(
        "file",
        type=Path,
    )

    args = parser.parse_args()

    if args.command == "classify":
        return validate_path(
            args.file,
            json_output=args.json,
        )

    return 1


if __name__ == "__main__":
    sys.exit(main())
