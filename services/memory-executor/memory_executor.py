#!/usr/bin/env python3

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any


SUPPORTED_SCHEMA = "0.2"

REQUIRED_INFORMATION_FIELDS = (
    "identity",
    "classification",
    "context",
    "provenance",
    "evidence",
    "time",
    "relations",
    "triggers",
    "retention",
    "content",
    "source",
)

OPERATIONS = (
    "STORE",
    "UPDATE",
    "INDEX",
    "IGNORE",
)


def make_operation_id(plan: dict[str, Any]) -> str:
    payload = json.dumps(
        plan,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )

    digest = hashlib.sha256(
        payload.encode("utf-8")
    ).hexdigest()

    return f"op-{digest}"


def load_plan(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise ValueError(
            f"Memory Plan introuvable : {path}"
        )

    try:
        data = json.loads(
            path.read_text(encoding="utf-8")
        )
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(
            f"Memory Plan JSON invalide : {exc}"
        ) from exc

    if not isinstance(data, dict):
        raise ValueError(
            "Memory Plan invalide : objet JSON attendu."
        )

    return data


def validate_plan(
    data: dict[str, Any],
) -> dict[str, Any]:

    if "memory_plan" not in data:
        raise ValueError(
            "Champ memory_plan absent."
        )

    plan = data["memory_plan"]

    if not isinstance(plan, dict):
        raise ValueError(
            "memory_plan doit être un objet."
        )

    schema = plan.get(
        "schema_version"
    )

    if schema != SUPPORTED_SCHEMA:
        raise ValueError(
            "Schema non supporté : "
            f"{schema!r}. "
            f"Version attendue : {SUPPORTED_SCHEMA}."
        )

    information = plan.get(
        "information"
    )

    if not isinstance(information, dict):
        raise ValueError(
            "Champ information absent ou invalide."
        )

    missing = [
        field
        for field in REQUIRED_INFORMATION_FIELDS
        if field not in information
    ]

    if missing:
        raise ValueError(
            "Information incomplète. "
            "Champs manquants : "
            + ", ".join(missing)
        )

    identity = information["identity"]

    if not isinstance(identity, dict):
        raise ValueError(
            "information.identity invalide."
        )

    if not identity.get("id"):
        raise ValueError(
            "information.identity.id absent."
        )

    revision = identity.get(
        "revision"
    )

    if not isinstance(revision, dict):
        raise ValueError(
            "information.identity.revision invalide."
        )

    if "number" not in revision:
        raise ValueError(
            "information.identity.revision.number absent."
        )

    classification = information[
        "classification"
    ]

    if not isinstance(
        classification,
        dict,
    ):
        raise ValueError(
            "information.classification invalide."
        )

    operations = plan.get(
        "operations"
    )

    if not isinstance(
        operations,
        dict,
    ):
        raise ValueError(
            "Champ operations absent ou invalide."
        )

    for operation in OPERATIONS:

        if operation not in operations:
            raise ValueError(
                f"Opération {operation} absente."
            )

        value = operations[
            operation
        ]

        if not isinstance(
            value,
            dict,
        ):
            raise ValueError(
                f"Opération {operation} invalide."
            )

        if "required" not in value:
            raise ValueError(
                f"Opération {operation} : "
                "champ required absent."
            )

        if "reason" not in value:
            raise ValueError(
                f"Opération {operation} : "
                "champ reason absent."
            )

    return plan


def prepare_operation(
    operation: str,
    definition: dict[str, Any],
    revision: dict[str, Any],
) -> dict[str, Any]:

    required = bool(
        definition["required"]
    )

    reason = definition[
        "reason"
    ]

    if not required:
        return {
            "required": False,
            "status": "NOT_REQUESTED",
            "reason": reason,
        }

    if operation == "STORE":
        return {
            "required": True,
            "status": "READY",
            "reason": reason,
        }

    if operation == "UPDATE":

        if revision.get(
            "is_revision"
        ) is not True:

            return {
                "required": True,
                "status": "BLOCKED",
                "reason": (
                    "UPDATE demandé sans "
                    "revision.is_revision = true."
                ),
            }

        if revision.get(
            "previous_revision"
        ) is None:

            return {
                "required": True,
                "status": "BLOCKED",
                "reason": (
                    "UPDATE demandé sans "
                    "previous_revision."
                ),
            }

        return {
            "required": True,
            "status": "READY",
            "reason": reason,
        }

    if operation == "INDEX":
        return {
            "required": True,
            "status": "PENDING",
            "reason": reason,
        }

    if operation == "IGNORE":
        return {
            "required": True,
            "status": "IGNORED",
            "reason": reason,
        }

    raise ValueError(
        f"Opération inconnue : {operation}"
    )


def check_contradictions(
    operations: dict[str, Any],
) -> None:

    store = bool(
        operations["STORE"]["required"]
    )

    update = bool(
        operations["UPDATE"]["required"]
    )

    index = bool(
        operations["INDEX"]["required"]
    )

    ignore = bool(
        operations["IGNORE"]["required"]
    )

    if ignore and (
        store
        or update
        or index
    ):
        raise ValueError(
            "Plan contradictoire : "
            "IGNORE et une autre opération "
            "sont simultanément requises."
        )


def build_execution_plan(
    plan: dict[str, Any],
) -> dict[str, Any]:

    information = plan[
        "information"
    ]

    operations = plan[
        "operations"
    ]

    revision = information[
        "identity"
    ][
        "revision"
    ]

    check_contradictions(
        operations
    )

    operation_id = make_operation_id(plan)

    execution = {
        "execution_plan": {
            "schema_version": "0.3",

            "operation_id": operation_id,

            "executor": {
                "component": (
                    "memory-executor"
                ),
                "version": "0.3",
                "mode": "DRY-RUN",
            },

            "input": {
                "memory_plan_schema": (
                    plan["schema_version"]
                ),
                "information_id": (
                    information[
                        "identity"
                    ]["id"]
                ),
                "revision": revision,
                "source_path": (
                    information[
                        "source"
                    ]["path"]
                ),
                "mechanisms": plan.get(
                    "mechanisms",
                    {},
                ),
            },

            "operations": {},

            "safety": {
                "writes_performed": False,
                "llm_used": False,
                "qdrant_used": False,
                "embedding_generated": False,
                "source_file_read": False,
            },
        }
    }

    for operation in OPERATIONS:

        execution[
            "execution_plan"
        ][
            "operations"
        ][operation] = prepare_operation(
            operation,
            operations[operation],
            revision,
        )

    return execution


def print_execution_plan(
    execution: dict[str, Any],
) -> None:

    print()
    print("=" * 60)
    print("Eidolon Memory Executor v0.3")
    print("=" * 60)
    print()

    print(
        json.dumps(
            execution,
            ensure_ascii=False,
            indent=2,
        )
    )

    print()
    print("=" * 60)
    print("Mode        : DRY-RUN")
    print("Writes      : NO")
    print("Source read : NO")
    print("LLM         : NO")
    print("Qdrant      : NO")
    print("Embedding   : NO")
    print("=" * 60)


def main() -> int:

    parser = argparse.ArgumentParser(
        description=(
            "Eidolon Memory Executor v0.3"
        )
    )

    sub = parser.add_subparsers(
        dest="command",
        required=True,
    )

    execute = sub.add_parser(
        "execute",
        help=(
            "Execute a Memory Plan "
            "in DRY-RUN mode."
        ),
    )

    execute.add_argument(
        "plan",
        type=Path,
    )

    args = parser.parse_args()

    if args.command != "execute":
        return 1

    try:

        data = load_plan(
            args.plan
        )

        plan = validate_plan(
            data
        )

        execution = (
            build_execution_plan(
                plan
            )
        )

    except (
        OSError,
        ValueError,
    ) as exc:

        print(
            f"ERREUR : {exc}",
            file=sys.stderr,
        )

        return 1

    print_execution_plan(
        execution
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
