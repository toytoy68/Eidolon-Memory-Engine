#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml


ENGINE_ROOT = Path(
    __file__
).resolve().parents[2]

sys.path.insert(
    0,
    str(ENGINE_ROOT)
)

from core.config import (
    SERVICES_ROOT,
)

CLASSIFIER = (
    SERVICES_ROOT
    / "memory-classifier"
    / "eidolon-memory-classifier"
)

PERSISTENT_MECHANISMS = (
    "EPISODIC",
    "SEMANTIC",
    "ASSOCIATIVE",
    "PROCEDURAL",
    "PROSPECTIVE",
)


def parse_information(
    text: str,
) -> tuple[dict[str, Any], str, str]:

    if not text.startswith("---\n"):
        raise ValueError("front matter absent")

    parts = text.split("---\n", 2)

    if len(parts) < 3:
        raise ValueError("front matter incomplet")

    front_matter_text = parts[1]
    content = parts[2].lstrip("\n")

    try:
        metadata = yaml.safe_load(front_matter_text)
    except yaml.YAMLError as exc:
        raise ValueError(
            f"front matter YAML invalide : {exc}"
        ) from exc

    if not isinstance(metadata, dict):
        raise ValueError(
            "front matter YAML invalide : objet attendu"
        )

    return metadata, content, front_matter_text


def normalize_for_json(
    value: Any,
) -> Any:

    if value is None:
        return None

    if isinstance(value, dict):
        return {
            str(key): normalize_for_json(item)
            for key, item in value.items()
        }

    if isinstance(value, list):
        return [
            normalize_for_json(item)
            for item in value
        ]

    if hasattr(value, "isoformat"):
        return value.isoformat()

    return value


def build_revision(
    metadata: dict[str, Any],
) -> dict[str, Any]:

    revision = metadata.get(
        "revision",
        1,
    )

    if isinstance(revision, dict):

        number = revision.get(
            "number"
        )

        is_revision = revision.get(
            "is_revision",
            False,
        )

        previous_revision = revision.get(
            "previous_revision"
        )

    else:

        number = revision

        is_revision = metadata.get(
            "is_revision",
            False,
        )

        previous_revision = metadata.get(
            "previous_revision"
        )

    if isinstance(is_revision, str):
        is_revision = (
            is_revision.lower()
            in {
                "true",
                "yes",
                "1",
            }
        )

    return {
        "number": number,
        "is_revision": bool(
            is_revision
        ),
        "previous_revision": (
            previous_revision
        ),
    }


def run_classifier(
    path: Path,
) -> dict[str, Any]:

    if not CLASSIFIER.is_file():
        raise RuntimeError(
            f"Classifier 21 introuvable : {CLASSIFIER}"
        )

    command = [
        str(CLASSIFIER),
        "classify",
        "--json",
        str(path),
    ]

    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
    except OSError as exc:
        raise RuntimeError(
            f"Impossible d'exécuter le Classifier 21 : {exc}"
        ) from exc

    if result.returncode != 0:

        error = (
            result.stderr.strip()
            or result.stdout.strip()
        )

        raise RuntimeError(
            f"Le Classifier 21 a échoué : {error}"
        )

    try:
        return json.loads(
            result.stdout
        )
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            "La sortie du Classifier 21 "
            "n'est pas un JSON valide."
        ) from exc


def build_plan(
    path: Path,
    metadata: dict[str, Any],
    content: str,
    front_matter_text: str,
    classifier_result: dict[str, Any],
) -> dict[str, Any]:

    information = classifier_result.get(
        "information",
        {}
    )

    classification = classifier_result.get(
        "classification",
        {}
    )

    revision = build_revision(
        metadata
    )

    confirmed = []
    possible = []
    rejected = []

    for mechanism, value in classification.items():

        status = value.get(
            "status"
        )

        if status == "YES":

            if mechanism != "WORKING":
                confirmed.append(
                    mechanism
                )

        elif status == "POSSIBLE":

            possible.append(
                mechanism
            )

        elif status == "NO":

            rejected.append(
                mechanism
            )

    update_required = revision[
        "is_revision"
    ]

    store_required = not update_required

    index_required = any(
        mechanism in confirmed
        for mechanism in PERSISTENT_MECHANISMS
    )

    if update_required:

        update_reason = (
            "Information explicitement "
            "marquée comme révision."
        )

    else:

        update_reason = (
            "Information non explicitement "
            "marquée comme révision."
        )

    if index_required:

        index_reason = (
            "Au moins un mécanisme mémoire "
            "persistant est classifié YES "
            "par le composant 21."
        )

    else:

        index_reason = (
            "Aucun mécanisme mémoire persistant "
            "n'est classifié YES par le composant 21."
        )

    normalized_metadata = normalize_for_json(
        metadata
    )

    reserved_fields = {
        "id",
        "revision",
        "type",
        "epistemic_status",
        "operational_state",
        "confidence",
        "importance",
        "is_revision",
        "previous_revision",
    }

    extra_metadata = {
        key: value
        for key, value in normalized_metadata.items()
        if key not in reserved_fields
    }

    information_object = {
        "identity": {
            "id": information.get(
                "id"
            ),
            "revision": revision,
        },

        "classification": {
            "type": information.get(
                "type"
            ),
            "epistemic_status": information.get(
                "epistemic_status",
                "UNKNOWN",
            ),
            "operational_state": information.get(
                "operational_state",
                "UNKNOWN",
            ),
            "confidence": metadata.get(
                "confidence"
            ),
            "importance": metadata.get(
                "importance"
            ),
        },

        "context": extra_metadata.get(
            "context",
            {}
        ),

        "provenance": extra_metadata.get(
            "provenance",
            {}
        ),

        "evidence": extra_metadata.get(
            "evidence",
            {}
        ),

        "time": extra_metadata.get(
            "time",
            {}
        ),

        "relations": extra_metadata.get(
            "relations",
            []
        ),

        "triggers": extra_metadata.get(
            "triggers",
            []
        ),

        "retention": extra_metadata.get(
            "retention"
        ),

        "content": content,

        "source": {
            "path": str(path),
            "front_matter": front_matter_text,
            "content": content,
        },
    }

    plan = {
        "memory_plan": {
            "schema_version": "0.2",

            "information": information_object,

            "classification": classification,

            "mechanisms": {
                "confirmed": confirmed,
                "possible": possible,
                "rejected": rejected,
            },

            "operations": {
                "STORE": {
                    "required": store_required,
                    "reason": (
                        "Information admissible "
                        "pour la mémoire persistante."
                    ),
                },

                "UPDATE": {
                    "required": update_required,
                    "reason": update_reason,
                },

                "INDEX": {
                    "required": index_required,
                    "reason": index_reason,
                },

                "IGNORE": {
                    "required": False,
                    "reason": (
                        "Une opération mémoire "
                        "est requise."
                    ),
                },
            },

            "safety": {
                "writes_performed": False,
                "llm_used": False,
                "qdrant_used": False,
                "embedding_generated": False,
            },
        }
    }

    return plan


def print_plan(
    plan: dict[str, Any],
) -> None:

    print()
    print("=" * 60)
    print("Eidolon Memory Router v0.2")
    print("=" * 60)
    print()

    print(
        json.dumps(
            plan,
            ensure_ascii=False,
            indent=2,
        )
    )

    print()
    print("=" * 60)
    print("Mode        : PLAN ONLY")
    print("Writes      : NO")
    print("LLM         : NO")
    print("Qdrant      : NO")
    print("Embedding   : NO")
    print("=" * 60)


def main() -> int:

    parser = argparse.ArgumentParser(
        description=(
            "Eidolon Memory Router v0.2"
        )
    )

    sub = parser.add_subparsers(
        dest="command",
        required=True,
    )

    route_parser = sub.add_parser(
        "route",
        help=(
            "Build a deterministic "
            "Memory Plan."
        ),
    )

    route_parser.add_argument(
        "information",
        type=Path,
    )

    args = parser.parse_args()

    if args.command != "route":
        return 1

    path = args.information

    if not path.is_file():

        print(
            f"ERREUR : Information introuvable : {path}",
            file=sys.stderr,
        )

        return 1

    try:

        source_text = path.read_text(
            encoding="utf-8"
        )

        (
            metadata,
            content,
            front_matter_text,
        ) = parse_information(
            source_text
        )

        classifier_result = (
            run_classifier(path)
        )

        plan = build_plan(
            path,
            metadata,
            content,
            front_matter_text,
            classifier_result,
        )

    except (
        OSError,
        ValueError,
        RuntimeError,
    ) as exc:

        print(
            f"ERREUR : {exc}",
            file=sys.stderr,
        )

        return 1

    print_plan(plan)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
