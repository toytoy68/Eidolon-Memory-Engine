#!/usr/bin/env python3

from __future__ import annotations

import json
import argparse
import hashlib
import re
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path


ENGINE_ROOT = Path(
    __file__
).resolve().parents[2]

sys.path.insert(
    0,
    str(ENGINE_ROOT)
)

from core.config import (
    WORKING_ROOT,
    PERSISTENT_ROOT,
    HISTORY_ROOT,
    EVENTS_ROOT,
    REVIEWS_ROOT,
    OPERATIONS_ROOT,
)


ALLOWED_TYPES = {
    "FACT", "OBSERVATION", "EVENT", "HYPOTHESIS", "PREDICTION",
    "INTERPRETATION", "QUESTION", "DECISION", "CONSTRAINT",
    "PREFERENCE", "CONCEPT", "PROCEDURE",
}

ALLOWED_EPISTEMIC = {
    "UNKNOWN", "UNVERIFIED", "CONFIRMED", "REFUTED",
    "CONFLICTED", "SUPERSEDED",
}

ALLOWED_OPERATIONAL = {
    "ACTIVE", "PLANNED", "PENDING_REVIEW", "CANCELLED",
    "COMPLETED", "DEPRECATED",
}

REQUIRED_FIELDS = {
    "id", "revision", "type", "epistemic_status", "operational_state",
    "confidence", "importance", "context", "provenance", "evidence",
    "time", "relations", "triggers", "retention",
}


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def make_id(prefix: str) -> str:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return f"{prefix}-{stamp}-{uuid.uuid4().hex[:8]}"


def yaml_scalar(text: str) -> str:
    return text.replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ")


def build_information(
    info_id: str,
    content: str,
    info_type: str,
    context_mode: str,
    project: str,
    source_type: str,
    source: str,
) -> str:
    return f"""---
id: {info_id}
revision: 1
type: {info_type}
epistemic_status: UNVERIFIED
operational_state: ACTIVE
confidence: LOW
importance: NORMAL

context:
  mode: {context_mode}
  project: "{yaml_scalar(project)}"
  domain:
    - GENERAL

provenance:
  source_type: {source_type}
  source: "{yaml_scalar(source)}"

evidence:
  supporting: []
  contradicting: []

time:
  created_at: {now_iso()}

relations: []
triggers: []

retention: NORMAL
---

# Information

{content}
"""


def parse_front_matter(text: str) -> dict[str, str]:
    lines = text.splitlines()

    if not lines or lines[0].strip() != "---":
        raise ValueError("front matter YAML absent")

    try:
        end = lines.index("---", 1)
    except ValueError as exc:
        raise ValueError("fin du front matter YAML absente") from exc

    result: dict[str, str] = {}

    for line in lines[1:end]:
        if not line.strip():
            continue

        match = re.match(
            r"^([A-Za-z_][A-Za-z0-9_]*):(?:\s*)(.*)$",
            line,
        )

        if match:
            key, value = match.groups()
            result[key] = value.strip()

    return result


def validate_information(path: Path) -> tuple[bool, list[str], dict[str, str]]:
    text = path.read_text(encoding="utf-8")
    fields = parse_front_matter(text)
    errors: list[str] = []

    missing = sorted(REQUIRED_FIELDS - set(fields))
    if missing:
        errors.append("champs absents : " + ", ".join(missing))

    if fields.get("type") and fields["type"] not in ALLOWED_TYPES:
        errors.append(f"type invalide : {fields['type']}")

    if fields.get("epistemic_status") and fields["epistemic_status"] not in ALLOWED_EPISTEMIC:
        errors.append(f"epistemic_status invalide : {fields['epistemic_status']}")

    if fields.get("operational_state") and fields["operational_state"] not in ALLOWED_OPERATIONAL:
        errors.append(f"operational_state invalide : {fields['operational_state']}")

    if not fields.get("id"):
        errors.append("id vide")

    return not errors, errors, fields


def replace_top_level(key: str, value: str, source: str) -> str:
    pattern = rf"^({re.escape(key)}:\s*).*$"

    if not re.search(pattern, source, flags=re.MULTILINE):
        raise ValueError(f"champ absent : {key}")

    return re.sub(
        pattern,
        rf"\g<1>{value}",
        source,
        count=1,
        flags=re.MULTILINE,
    )

def create_event(
    information_id: str,
    revision: int,
    event_type: str,
    initial_epistemic: str,
    initial_operational: str,
    reason: str,
    operation_id: str | None = None,
) -> Path:

    event_id = make_id("event")
    event_path = EVENTS_ROOT / f"{event_id}.md"

    operation_relation = ""

    if operation_id:
      operation_relation = f"""    - type: CAUSED_BY_OPERATION
      target: {operation_id}
"""

    event_content = f"""---
event_id: {event_id}
information_id: {information_id}
revision: {revision}

event_type: {event_type}

state:
  initial:
    epistemic_status: {initial_epistemic}
    operational_state: {initial_operational}

cause:
  type: {"MEMORY_OPERATION" if event_type == "STORED" else "NEW_INFORMATION"}
  description: "{yaml_scalar(reason)}"

evidence:
  supporting: []
  contradicting: []

provenance:
  source_type: SYSTEM_GENERATED
  source: memory-controller
  actor: eidolon
  timestamp: {now_iso()}

validation:
  mode: AUTOMATIC
  status: ACCEPTED

relations:
  - type: CONCERNS
    target: {information_id}
{operation_relation}
---

# Memory Event

{yaml_scalar(reason)}
"""

    event_path.write_text(
        event_content,
        encoding="utf-8",
    )

    return event_path


def create_review(information_id: str, reason: str) -> Path:
    review_id = make_id("review")
    review_path = REVIEWS_ROOT / f"{review_id}.md"

    content = (
        "---\n"
        f"review_id: {review_id}\n"
        f"information_id: {information_id}\n"
        f"created_at: {now_iso()}\n"
        "status: PENDING_REVIEW\n"
        f"reason: \"{yaml_scalar(reason)}\"\n"
        "---\n\n"
        "# Administrative Review\n\n"
        "Cette information nécessite une décision humaine.\n\n"
        "Le contrôleur ne doit pas forcer une transition lorsqu'un doute\n"
        "persiste.\n"
    )

    review_path.write_text(content, encoding="utf-8")
    return review_path


def ingest(args: argparse.Namespace) -> int:
    info_type = args.type.upper()

    if info_type not in ALLOWED_TYPES:
        print(f"ERREUR : type invalide : {info_type}")
        return 1

    info_id = make_id("info")
    path = WORKING_ROOT / f"{info_id}.md"

    content = build_information(
        info_id,
        args.content,
        info_type,
        args.mode.upper(),
        args.project,
        args.source_type.upper(),
        args.source,
    )

    if path.exists():
        print(f"ERREUR : collision d'identifiant : {path}")
        return 1

    path.write_text(content, encoding="utf-8")

    valid, errors, fields = validate_information(path)

    if not valid:
        path.unlink(missing_ok=True)
        print("ERREUR : information rejetée.")
        for error in errors:
            print(f"- {error}")
        return 1

    event = create_event(
        fields["id"],
        1,
        "CREATED",
        fields["epistemic_status"],
        fields["operational_state"],
        "Nouvelle information reçue dans Working Memory.",
    )

    review = None

    if info_type == "DECISION" or fields["epistemic_status"] == "CONFLICTED":
        review = create_review(
            fields["id"],
            "Le prototype ne dispose pas encore des mécanismes suffisants "
            "pour valider automatiquement cette information.",
        )

    print(f"Information créée : {path}")
    print(f"ID : {info_id}")
    print(f"Type : {info_type}")
    print("État épistémique initial : UNVERIFIED")
    print("État opérationnel : ACTIVE")
    print("Validation structurelle : OK")
    print(f"Événement historique : {event}")

    if review:
        print(f"REVUE ADMINISTRATEUR : {review}")

    return 0


def update_information(
    path: Path,
    new_epistemic: str | None,
    new_operational: str | None,
    new_confidence: str | None,
    new_importance: str | None,
    reason: str,
    event_type: str,
    event_id_out: list[str] | None = None,
) -> int:
    if not path.is_file():
        print(f"ERREUR : information introuvable : {path}")
        return 1

    try:
        valid, errors, fields = validate_information(path)
        text = path.read_text(encoding="utf-8")
    except (OSError, ValueError) as exc:
        print(f"ERREUR : lecture impossible : {exc}")
        return 1

    if not valid:
        print("ERREUR : information actuelle invalide.")
        for error in errors:
            print(f"- {error}")
        return 1

    old_epistemic = fields["epistemic_status"]
    old_operational = fields["operational_state"]
    old_confidence = fields["confidence"]
    old_importance = fields["importance"]

    try:
        old_revision = int(fields["revision"])
    except ValueError:
        print(f"ERREUR : revision invalide : {fields['revision']}")
        return 1

    new_epistemic = new_epistemic or old_epistemic
    new_operational = new_operational or old_operational
    new_confidence = new_confidence or old_confidence
    new_importance = new_importance or old_importance

    if new_epistemic not in ALLOWED_EPISTEMIC:
        print(f"ERREUR : epistemic_status invalide : {new_epistemic}")
        return 1

    if new_operational not in ALLOWED_OPERATIONAL:
        print(f"ERREUR : operational_state invalide : {new_operational}")
        return 1

    new_revision = old_revision + 1
    updated = text

    try:
        updated = replace_top_level("revision", str(new_revision), updated)
        updated = replace_top_level("epistemic_status", new_epistemic, updated)
        updated = replace_top_level("operational_state", new_operational, updated)
        updated = replace_top_level("confidence", new_confidence, updated)
        updated = replace_top_level("importance", new_importance, updated)
    except ValueError as exc:
        print(f"ERREUR : mise à jour impossible : {exc}")
        return 1

    event_id = make_id("event")
    event_path = EVENTS_ROOT / f"{event_id}.md"

    if event_id_out is not None:
        event_id_out.append(event_id)

    event_content = f"""---
event_id: {event_id}
information_id: {fields["id"]}
revision: {new_revision}

event_type: {event_type}

state_transition:
  before:
    epistemic_status: {old_epistemic}
    operational_state: {old_operational}
  after:
    epistemic_status: {new_epistemic}
    operational_state: {new_operational}

metadata_transition:
  before:
    confidence: {old_confidence}
    importance: {old_importance}
  after:
    confidence: {new_confidence}
    importance: {new_importance}

cause:
  type: MANUAL_ACTION
  description: "{yaml_scalar(reason)}"

evidence:
  supporting: []
  contradicting: []

provenance:
  source_type: SYSTEM_GENERATED
  source: memory-controller
  actor: eidolon
  timestamp: {now_iso()}

validation:
  mode: HUMAN
  status: ACCEPTED

relations:
  - type: CONCERNS
    target: {fields["id"]}
---

# Memory Event

Transition de revision {old_revision} vers revision {new_revision}.
"""

    temp_path = path.with_suffix(path.suffix + ".tmp")

    try:
        event_path.write_text(event_content, encoding="utf-8")
        temp_path.write_text(updated, encoding="utf-8")
        temp_path.replace(path)
    except OSError as exc:
        event_path.unlink(missing_ok=True)
        temp_path.unlink(missing_ok=True)
        print(f"ERREUR : mise à jour annulée : {exc}")
        return 1

    print(f"Information mise à jour : {path}")
    print(f"ID : {fields['id']}")
    print(f"Revision : {old_revision} -> {new_revision}")
    print(f"Epistemic status : {old_epistemic} -> {new_epistemic}")
    print(f"Operational state : {old_operational} -> {new_operational}")
    print(f"Event historique : {event_path}")

    return 0

def resolve_review(review_path: Path, decision: str, reason: str) -> int:
    decision = decision.upper()
    allowed = {"CONFIRMED", "REFUTED", "CONFLICTED"}

    if decision not in allowed:
        print(f"ERREUR : décision invalide : {decision}")
        print("Décisions autorisées : CONFIRMED, REFUTED, CONFLICTED")
        return 1

    if not review_path.is_file():
        print(f"ERREUR : Review introuvable : {review_path}")
        return 1

    try:
        review_text = review_path.read_text(encoding="utf-8")
        review_fields = parse_front_matter(review_text)
    except (OSError, ValueError) as exc:
        print(f"ERREUR : Review invalide : {exc}")
        return 1

    if review_fields.get("status") != "PENDING_REVIEW":
        print(
            "ERREUR : Review non résoluble : "
            f"{review_fields.get('status', 'UNKNOWN')}"
        )
        return 1

    information_id = review_fields.get("information_id")
    if not information_id:
        print("ERREUR : information_id absent de la Review.")
        return 1

    information_path = WORKING_ROOT / f"{information_id}.md"
    if not information_path.is_file():
        print(f"ERREUR : Information liée introuvable : {information_path}")
        return 1

    valid, errors, fields = validate_information(information_path)
    if not valid:
        print("ERREUR : Information liée invalide.")
        for error in errors:
            print(f"- {error}")
        return 1

    if fields.get("id") != information_id:
        print("ERREUR : incohérence entre Review et Information.")
        return 1

    if fields.get("epistemic_status") != "UNVERIFIED":
        print(
            "ERREUR : l'Information n'est plus UNVERIFIED : "
            f"{fields.get('epistemic_status')}"
        )
        return 1

    resolution_event_id: list[str] = []

    result = update_information(
        information_path,
        decision,
        None,
        None,
        None,
        reason,
        "REVIEW_RESOLVED",
        resolution_event_id,

    )

    if result != 0:
        print("ERREUR : résolution de Review annulée.")
        return result

    if len(resolution_event_id) != 1:
        print("ERREUR : Event de résolution introuvable.")
        return 1

    resolution_event = resolution_event_id[0]


    timestamp = now_iso()
    updated_review = review_text

    try:
        updated_review = replace_top_level("status", "RESOLVED", updated_review)

        if re.search(r"^decision:\s*.*$", updated_review, flags=re.MULTILINE):
            updated_review = replace_top_level("decision", decision, updated_review)
        else:
            updated_review = updated_review.replace(
                "---\n", f"---\ndecision: {decision}\n", 1
            )

        if re.search(r"^resolved_at:\s*.*$", updated_review, flags=re.MULTILINE):
            updated_review = replace_top_level("resolved_at", timestamp, updated_review)
        else:
            updated_review = updated_review.replace(
                "---\n", f"---\nresolved_at: {timestamp}\n", 1
            )

        if re.search(r"^resolver:\s*.*$", updated_review, flags=re.MULTILINE):
            updated_review = replace_top_level("resolver", "human", updated_review)
        else:
            updated_review = updated_review.replace(
                "---\n", "---\nresolver: human\n", 1
            )

        tmp = review_path.with_suffix(review_path.suffix + ".tmp")
        if re.search(r"^resolution_event_id:\s*.*$", updated_review, flags=re.MULTILINE):
            updated_review = replace_top_level("resolution_event_id", resolution_event, updated_review)
        else:
            updated_review = updated_review.replace(
                "---\n",
                f"---\nresolution_event_id: {resolution_event}\n",
                1,
            )

        tmp.write_text(updated_review, encoding="utf-8")
        tmp.replace(review_path)

    except OSError as exc:
        print(
            "ATTENTION : Information mise à jour, mais Review non résolue : "
            f"{exc}"
        )
        return 1

    print(f"Review résolue : {review_path}")
    print(f"Information : {information_id}")
    print(f"Décision : {decision}")
    print("Statut Review : PENDING_REVIEW -> RESOLVED")
    print("Événement : REVIEW_RESOLVED")
    return 0


def validate_file(path: Path) -> int:
    try:
        valid, errors, fields = validate_information(path)
    except (OSError, ValueError) as exc:
        print(f"ERREUR : {path}")
        print(f"- {exc}")
        return 1

    if valid:
        print(f"OK : {path}")
        print(f"ID : {fields.get('id')}")
        print(f"Revision : {fields.get('revision')}")
        print(f"Type : {fields.get('type')}")
        print(f"Epistemic status : {fields.get('epistemic_status')}")
        print(f"Operational state : {fields.get('operational_state')}")
        return 0

    print(f"ERREUR : {path}")
    for error in errors:
        print(f"- {error}")
    return 1


EXECUTION_PLAN_SCHEMA = "0.3"


def load_execution_plan(
    path: Path,
) -> dict[str, Any]:

    if not path.is_file():
        raise ValueError(
            f"Execution Plan introuvable : {path}"
        )

    try:
        data = json.loads(
            path.read_text(
                encoding="utf-8"
            )
        )
    except (
        OSError,
        json.JSONDecodeError,
    ) as exc:
        raise ValueError(
            f"Execution Plan JSON invalide : {exc}"
        ) from exc

    if not isinstance(data, dict):
        raise ValueError(
            "Execution Plan invalide : "
            "objet JSON attendu."
        )

    return data


def validate_execution_plan(
    data: dict[str, Any],
) -> dict[str, Any]:

    execution = data.get(
        "execution_plan"
    )

    if not isinstance(
        execution,
        dict,
    ):
        raise ValueError(
            "Champ execution_plan absent "
            "ou invalide."
        )

    schema = execution.get(
        "schema_version"
    )

    if schema != EXECUTION_PLAN_SCHEMA:
        raise ValueError(
            "Execution Plan schema non supporté : "
            f"{schema!r}. "
            f"Version attendue : "
            f"{EXECUTION_PLAN_SCHEMA}."
        )

    operation_id = execution.get(
        "operation_id"
    )

    if not isinstance(
        operation_id,
        str,
    ) or not operation_id:
        raise ValueError(
            "Execution Plan : "
            "operation_id absent ou invalide."
        )

    input_data = execution.get(
        "input"
    )

    if not isinstance(
        input_data,
        dict,
    ):
        raise ValueError(
            "Execution Plan : "
            "input absent ou invalide."
        )

    information_id = input_data.get(
        "information_id"
    )

    if not isinstance(
        information_id,
        str,
    ) or not information_id:
        raise ValueError(
            "Execution Plan : "
            "information_id absent ou invalide."
        )

    revision = input_data.get(
        "revision"
    )

    if not isinstance(
        revision,
        dict,
    ):
        raise ValueError(
            "Execution Plan : "
            "revision absente ou invalide."
        )

    operations = execution.get(
        "operations"
    )

    if not isinstance(
        operations,
        dict,
    ):
        raise ValueError(
            "Execution Plan : "
            "operations absentes ou invalides."
        )

    required_operations = (
        "STORE",
        "UPDATE",
        "INDEX",
        "IGNORE",
    )

    for operation in required_operations:

        if operation not in operations:
            raise ValueError(
                "Execution Plan : "
                f"opération {operation} absente."
            )

    return execution

def inspect_persistent_state(
    information_id: str,
) -> dict[str, Any]:

    information_path = (
        PERSISTENT_ROOT
        / f"{information_id}.md"
    )

    if not information_path.is_file():
        return {
            "exists": False,
            "information_id": information_id,
            "path": str(information_path),
            "revision": None,
        }

    try:
        text = information_path.read_text(
            encoding="utf-8"
        )
    except OSError as exc:
        raise ValueError(
            "Impossible de lire "
            f"l'Information persistante : {exc}"
        ) from exc

    fields = parse_front_matter(text)

    revision = fields.get(
        "revision"
    )

    revision_match = re.search(
        r"(?m)^revision:\s*\n"
        r"\s+number:\s*(\d+)",
        text,
    )

    if revision_match is not None:
        revision = revision_match.group(1)

    return {
        "exists": True,
        "information_id": information_id,
        "path": str(information_path),
        "revision": revision,
    }


def evaluate_execution_plan(
    execution: dict[str, Any],
) -> dict[str, Any]:

    operation_id = execution[
        "operation_id"
    ]

    information_id = execution[
        "input"
    ][
        "information_id"
    ]

    operations = execution[
        "operations"
    ]

    idempotency = (
        inspect_operation_idempotency(
            execution
        )
    )

    state = inspect_persistent_state(
        information_id
    )

    if idempotency["state"] == "CONFLICT":

        return {
            "result": "BLOCK",
            "reason": (
                "operation_id déjà associé "
                "à une autre opération logique."
            ),
            "operation_id": operation_id,
            "information_id": information_id,
            "idempotency": idempotency,
            "persistent_state": state,
            "writes_performed": False,
        }

    if idempotency["state"] == "ALREADY_EXECUTED":

        return {
            "result": "NO-OP",
            "reason": (
                "Cette opération a déjà été "
                "exécutée avec le même "
                "Execution Plan."
            ),
            "operation_id": operation_id,
            "information_id": information_id,
            "idempotency": idempotency,
            "persistent_state": state,
            "writes_performed": False,
        }

    if (
        idempotency["state"] == "NEW"
        and operations["UPDATE"]["required"]
        and state["exists"]
    ):
        revision = execution[
            "input"
        ][
            "revision"
        ]

        if (
            state.get("revision")
            == str(revision["number"])
            and revision.get("previous_revision")
            is not None
        ):
            idempotency = {
                **idempotency,
                "state": "PARTIAL",
            }

            return {
                "result": "ALLOW",
                "reason": (
                    "UPDATE partiellement exécutée : "
                    "Persistent Memory contient déjà "
                    "la révision demandée. "
                    "Finalisation autorisée."
                ),
                "operation_id": operation_id,
                "information_id": information_id,
                "idempotency": idempotency,
                "persistent_state": state,
                "writes_performed": False,
            }

    store = operations[
        "STORE"
    ]

    update = operations[
        "UPDATE"
    ]

    index = operations[
        "INDEX"
    ]

    ignore = operations[
        "IGNORE"
    ]

    if ignore["required"]:

        if (
            store["required"]
            or update["required"]
            or index["required"]
        ):
            return {
                "result": "BLOCK",
                "reason": (
                    "IGNORE est contradictoire "
                    "avec une autre opération."
                ),
                "operation_id": operation_id,
                "information_id": information_id,
                "idempotency": idempotency,
                "persistent_state": state,
                "writes_performed": False,
            }

        return {
            "result": "NO-OP",
            "reason": (
                "IGNORE est la seule "
                "opération requise."
            ),
            "operation_id": operation_id,
            "information_id": information_id,
            "idempotency": idempotency,
            "persistent_state": state,
            "writes_performed": False,
        }

    if update["required"]:

        revision = execution[
            "input"
        ][
            "revision"
        ]

        if revision.get(
            "previous_revision"
        ) is None:
            return {
                "result": "BLOCK",
                "reason": (
                    "UPDATE demandé sans "
                    "previous_revision."
                ),
                "operation_id": operation_id,
                "information_id": information_id,
                "idempotency": idempotency,
                "persistent_state": state,
                "writes_performed": False,
            }

        if not state["exists"]:
            return {
                "result": "BLOCK",
                "reason": (
                    "UPDATE demandé mais "
                    "l'Information persistante "
                    "n'existe pas."
                ),
                "operation_id": operation_id,
                "information_id": information_id,
                "idempotency": idempotency,
                "persistent_state": state,
                "writes_performed": False,
            }

        return {
            "result": "ALLOW",
            "reason": (
                "UPDATE demandé et "
                "Information persistante existante."
            ),
            "operation_id": operation_id,
            "information_id": information_id,
            "idempotency": idempotency,
            "persistent_state": state,
            "writes_performed": False,
        }

    if store["required"]:

        if state["exists"]:

            return {
                "result": "BLOCK",
                "reason": (
                    "STORE demandé mais "
                    "l'Information existe déjà."
                ),
                "operation_id": operation_id,
                "information_id": information_id,
                "idempotency": idempotency,
                "persistent_state": state,
                "writes_performed": False,
            }

        return {
            "result": "ALLOW",
            "reason": (
                "STORE demandé et "
                "Information inexistante."
            ),
            "operation_id": operation_id,
            "information_id": information_id,
            "idempotency": idempotency,
            "persistent_state": state,
            "writes_performed": False,
        }

    if index["required"]:

        return {
            "result": "ALLOW",
            "reason": (
                "INDEX demandé. "
                "Aucune écriture de contenu "
                "n'est effectuée par cette "
                "évaluation."
            ),
            "operation_id": operation_id,
            "information_id": information_id,
            "idempotency": idempotency,
            "persistent_state": state,
            "writes_performed": False,
        }

    return {
        "result": "NO-OP",
        "reason": (
            "Aucune opération persistante "
            "requise."
        ),
        "operation_id": operation_id,
        "information_id": information_id,
        "idempotency": idempotency,
        "persistent_state": state,
        "writes_performed": False,
    }


def load_operation_record(
    operation_id: str,
) -> dict[str, Any] | None:

    operation_path = (
        OPERATIONS_ROOT
        / f"{operation_id}.json"
    )

    if not operation_path.is_file():
        return None

    try:
        data = json.loads(
            operation_path.read_text(
                encoding="utf-8"
            )
        )
    except (
        OSError,
        json.JSONDecodeError,
    ) as exc:
        raise ValueError(
            "Enregistrement d'opération invalide : "
            f"{operation_path} : {exc}"
        ) from exc

    if not isinstance(data, dict):
        raise ValueError(
            "Enregistrement d'opération invalide : "
            "objet JSON attendu."
        )

    stored_operation_id = data.get(
        "operation_id"
    )

    if stored_operation_id != operation_id:
        raise ValueError(
            "Conflit d'identité : "
            "operation_id du fichier différent "
            "de son nom."
        )

    return data

def hash_execution_plan(
    execution: dict[str, Any],
) -> str:

    payload = json.dumps(
        execution,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )

    return hashlib.sha256(
        payload.encode("utf-8")
    ).hexdigest()


def inspect_operation_idempotency(
    execution: dict[str, Any],
) -> dict[str, Any]:

    operation_id = execution[
        "operation_id"
    ]

    execution_hash = hash_execution_plan(
        execution
    )

    record = load_operation_record(
        operation_id
    )

    if record is None:
        return {
            "state": "NEW",
            "operation_id": operation_id,
            "execution_plan_hash": execution_hash,
        }

    stored_hash = record.get(
        "execution_plan_hash"
    )

    if stored_hash == execution_hash:
        return {
            "state": "ALREADY_EXECUTED",
            "operation_id": operation_id,
            "execution_plan_hash": execution_hash,
        }

    return {
        "state": "CONFLICT",
        "operation_id": operation_id,
        "execution_plan_hash": execution_hash,
        "stored_execution_plan_hash": stored_hash,
    }

def write_operation_record(
    execution: dict[str, Any],
    result: str,
) -> Path:

    operation_id = execution[
        "operation_id"
    ]

    execution_hash = hash_execution_plan(
        execution
    )

    OPERATIONS_ROOT.mkdir(
        parents=True,
        exist_ok=True,
    )

    operation_path = (
        OPERATIONS_ROOT
        / f"{operation_id}.json"
    )

    record = {
        "operation_id": operation_id,
        "execution_plan_hash": execution_hash,
        "information_id": execution[
            "input"
        ][
            "information_id"
        ],
        "result": result,
        "status": "EXECUTED",
        "timestamp": now_iso(),
    }

    temporary_path = operation_path.with_suffix(
        ".json.tmp"
    )

    temporary_path.write_text(
        json.dumps(
            record,
            ensure_ascii=False,
            indent=2,
        ) + "\n",
        encoding="utf-8",
    )

    temporary_path.replace(
        operation_path
    )

    return operation_path

def execute_store_operation(
    execution: dict[str, Any],
) -> dict[str, Any]:

    information_id = execution[
        "input"
    ][
        "information_id"
    ]

    source_path = Path(
        execution[
            "input"
        ][
            "source_path"
        ]
    )

    destination_path = (
        PERSISTENT_ROOT
        / f"{information_id}.md"
    )

    if destination_path.exists():
        raise ValueError(
            "STORE refusé : "
            "l'Information existe déjà dans "
            "Persistent Memory."
        )

    if not source_path.is_file():
        raise ValueError(
            "STORE refusé : "
            f"source absente : {source_path}"
        )

    try:
        valid, errors, fields = (
            validate_information(
                source_path
            )
        )
    except (
        OSError,
        ValueError,
    ) as exc:
        raise ValueError(
            "STORE refusé : "
            f"validation impossible : {exc}"
        ) from exc

    if not valid:
        raise ValueError(
            "STORE refusé : "
            "Information source invalide : "
            + "; ".join(errors)
        )

    if fields.get("id") != information_id:
        raise ValueError(
            "STORE refusé : "
            "information_id différent de "
            "l'ID du fichier source."
        )

    PERSISTENT_ROOT.mkdir(
        parents=True,
        exist_ok=True,
    )

    content = source_path.read_text(
        encoding="utf-8"
    )

    temporary_path = destination_path.with_suffix(
        ".md.tmp"
    )

    try:
        temporary_path.write_text(
            content,
            encoding="utf-8",
        )

        temporary_path.replace(
            destination_path
        )

    except OSError as exc:

        if temporary_path.exists():
            temporary_path.unlink()

        raise ValueError(
            "STORE échoué pendant "
            f"l'écriture : {exc}"
        ) from exc

    return {
        "result": "STORE",
        "information_id": information_id,
        "source_path": str(source_path),
        "destination_path": str(
            destination_path
        ),
        "writes_performed": True,
    }

def execute_update_operation(
    execution: dict[str, Any],
) -> dict[str, Any]:

    information_id = execution[
        "input"
    ][
        "information_id"
    ]

    source_path = Path(
        execution[
            "input"
        ][
            "source_path"
        ]
    )

    revision = execution[
        "input"
    ][
        "revision"
    ]

    expected_revision = revision[
        "number"
    ]

    previous_revision = revision[
        "previous_revision"
    ]

    destination_path = (
        PERSISTENT_ROOT
        / f"{information_id}.md"
    )

    if not source_path.is_file():
        raise ValueError(
            "UPDATE refusé : "
            f"source absente : {source_path}"
        )

    if not destination_path.is_file():
        raise ValueError(
            "UPDATE refusé : "
            "Information persistante absente : "
            f"{destination_path}"
        )

    try:
        source_valid, source_errors, source_fields = (
            validate_information(
                source_path
            )
        )
    except (
        OSError,
        ValueError,
    ) as exc:
        raise ValueError(
            "UPDATE refusé : "
            f"validation de la source impossible : {exc}"
        ) from exc

    if not source_valid:
        raise ValueError(
            "UPDATE refusé : "
            "Information source invalide : "
            + "; ".join(source_errors)
        )

    if source_fields.get("id") != information_id:
        raise ValueError(
            "UPDATE refusé : "
            "information_id différent de "
            "l'ID du fichier source."
        )

    source_text = source_path.read_text(
        encoding="utf-8"
    )

    revision_match = re.search(
        r"(?m)^revision:\s*\n"
        r"\s+number:\s*(\d+)",
        source_text,
    )

    if revision_match is None:
        raise ValueError(
            "UPDATE refusé : "
            "révision structurée absente ou invalide."
        )

    source_revision = int(
        revision_match.group(1)
    )

    if source_revision != expected_revision:
        raise ValueError(
            "UPDATE refusé : "
            f"révision source {source_revision} "
            f"différente de la révision demandée "
            f"{expected_revision}."
        )

    try:
        persistent_valid, persistent_errors, persistent_fields = (
            validate_information(
                destination_path
            )
        )
    except (
        OSError,
        ValueError,
    ) as exc:
        raise ValueError(
            "UPDATE refusé : "
            "validation de Persistent Memory impossible : "
            f"{exc}"
        ) from exc

    if not persistent_valid:
        raise ValueError(
            "UPDATE refusé : "
            "Information persistante invalide : "
            + "; ".join(persistent_errors)
        )

    if persistent_fields.get("id") != information_id:
        raise ValueError(
            "UPDATE refusé : "
            "information_id différent de "
            "l'ID de Persistent Memory."
        )

    persistent_text = destination_path.read_text(
        encoding="utf-8"
    )

    persistent_revision_match = re.search(
        r"(?m)^revision:\s*\n"
        r"\s+number:\s*(\d+)",
        persistent_text,
    )

    if persistent_revision_match is None:
        raise ValueError(
            "UPDATE refusé : "
            "révision persistante invalide."
        )

    persistent_revision = int(
        persistent_revision_match.group(1)
    )

    if persistent_revision != int(
        previous_revision
    ):
        raise ValueError(
            "UPDATE refusé : "
            f"révision persistante {persistent_revision} "
            f"différente de previous_revision "
            f"{previous_revision}."
        )

    content = source_path.read_text(
        encoding="utf-8"
    )

    temporary_path = destination_path.with_suffix(
        ".md.tmp"
    )

    try:
        temporary_path.write_text(
            content,
            encoding="utf-8",
        )

        temporary_path.replace(
            destination_path
        )

    except OSError as exc:

        if temporary_path.exists():
            temporary_path.unlink()

        raise ValueError(
            "UPDATE échoué pendant "
            f"l'écriture : {exc}"
        ) from exc

    return {
        "result": "UPDATE",
        "information_id": information_id,
        "source_path": str(source_path),
        "destination_path": str(
            destination_path
        ),
        "previous_revision": previous_revision,
        "new_revision": expected_revision,
        "writes_performed": True,
    }


def execute_execution_plan(
    execution: dict[str, Any],
) -> dict[str, Any]:

    decision = evaluate_execution_plan(
        execution
    )

    if decision["result"] != "ALLOW":
        return decision

    operations = execution[
        "operations"
    ]

    if operations["STORE"]["required"]:

        try:
            store_result = execute_store_operation(
                execution
            )

        except (
            OSError,
            ValueError,
        ) as exc:

            return {
                "result": "BLOCK",
                "reason": str(exc),
                "operation_id": execution[
                    "operation_id"
                ],
                "information_id": execution[
                    "input"
                ][
                    "information_id"
                ],
                "decision": decision,
                "writes_performed": False,
            }

        information_id = execution[
            "input"
        ][
            "information_id"
        ]

        persistent_state = (
            inspect_persistent_state(
                information_id
            )
        )

        if not persistent_state["exists"]:
            return {
                "result": "BLOCK",
                "reason": (
                    "STORE annoncé comme réussi "
                    "mais l'Information n'est pas "
                    "présente dans Persistent Memory."
                ),
                "operation_id": execution[
                    "operation_id"
                ],
                "information_id": information_id,
                "decision": decision,
                "writes_performed": False,
            }

        persistent_path = Path(
            persistent_state["path"]
        )

        try:
            valid, errors, fields = (
                validate_information(
                    persistent_path
                )
            )

        except (
            OSError,
            ValueError,
        ) as exc:

            return {
                "result": "BLOCK",
                "reason": (
                    "STORE effectué mais "
                    "validation de Persistent Memory "
                    f"impossible : {exc}"
                ),
                "operation_id": execution[
                    "operation_id"
                ],
                "information_id": information_id,
                "decision": decision,
                "persistent_state": persistent_state,
                "writes_performed": True,
            }

        if not valid:
            return {
                "result": "BLOCK",
                "reason": (
                    "STORE effectué mais "
                    "Information persistante invalide : "
                    + "; ".join(errors)
                ),
                "operation_id": execution[
                    "operation_id"
                ],
                "information_id": information_id,
                "decision": decision,
                "persistent_state": persistent_state,
                "writes_performed": True,
            }

        revision = execution[
            "input"
        ][
            "revision"
        ][
            "number"
        ]

        event_path = create_event(
            information_id,
            revision,
            "STORED",
            fields.get(
                "epistemic_status",
                "UNVERIFIED",
            ),
            fields.get(
                "operational_state",
                "ACTIVE",
            ),
            "Information persistée dans Persistent Memory.",
            operation_id=execution[
                "operation_id"
            ],
        )

        operation_path = write_operation_record(
            execution,
            "STORE",
        )

        return {
            "result": "STORE",
            "reason": (
                "Information persistée avec succès."
            ),
            "operation_id": execution[
                "operation_id"
            ],
            "information_id": information_id,
            "store": store_result,
            "persistent_state": persistent_state,
            "event": str(event_path),
            "operation_record": str(
                operation_path
            ),
            "writes_performed": True,
        }

    if operations["UPDATE"]["required"]:

        partial_update = (
            decision.get("idempotency", {}).get(
                "state"
            ) == "PARTIAL"
        )

        if partial_update:

            information_id = execution[
                "input"
            ][
                "information_id"
            ]

            revision = execution[
                "input"
            ][
                "revision"
            ]

            update_result = {
                "result": "UPDATE",
                "information_id": information_id,
                "source_path": execution[
                    "input"
                ][
                    "source_path"
                ],
                "destination_path": str(
                    PERSISTENT_ROOT
                    / f"{information_id}.md"
                ),
                "previous_revision": revision[
                    "previous_revision"
                ],
                "new_revision": revision[
                    "number"
                ],
                "writes_performed": False,
                "resumed": True,
            }

        else:

            try:
                update_result = execute_update_operation(
                    execution
                )

            except (
                OSError,
                ValueError,
            ) as exc:

                return {
                    "result": "BLOCK",
                    "reason": str(exc),
                    "operation_id": execution[
                        "operation_id"
                    ],
                    "information_id": execution[
                        "input"
                    ][
                        "information_id"
                    ],
                    "decision": decision,
                    "writes_performed": False,
                }

        information_id = execution[
            "input"
        ][
            "information_id"
        ]

        persistent_state = (
            inspect_persistent_state(
                information_id
            )
        )

        if not persistent_state["exists"]:
            return {
                "result": "BLOCK",
                "reason": (
                    "UPDATE annoncé comme réussi "
                    "mais l'Information n'est pas "
                    "présente dans Persistent Memory."
                ),
                "operation_id": execution[
                    "operation_id"
                ],
                "information_id": information_id,
                "decision": decision,
                "writes_performed": True,
            }

        persistent_path = Path(
            persistent_state["path"]
        )

        try:
            valid, errors, fields = (
                validate_information(
                    persistent_path
                )
            )

        except (
            OSError,
            ValueError,
        ) as exc:

            return {
                "result": "BLOCK",
                "reason": (
                    "UPDATE effectué mais "
                    "validation de Persistent Memory "
                    f"impossible : {exc}"
                ),
                "operation_id": execution[
                    "operation_id"
                ],
                "information_id": information_id,
                "persistent_state": persistent_state,
                "writes_performed": True,
            }

        if not valid:
            return {
                "result": "BLOCK",
                "reason": (
                    "UPDATE effectué mais "
                    "Information persistante invalide : "
                    + "; ".join(errors)
                ),
                "operation_id": execution[
                    "operation_id"
                ],
                "information_id": information_id,
                "persistent_state": persistent_state,
                "writes_performed": True,
            }

        revision = execution[
            "input"
        ][
            "revision"
        ][
            "number"
        ]

        if persistent_state.get("revision") != str(
            revision
        ):
            return {
                "result": "BLOCK",
                "reason": (
                    "UPDATE effectué mais "
                    "la révision persistante obtenue "
                    "ne correspond pas à la révision "
                    "demandée."
                ),
                "operation_id": execution[
                    "operation_id"
                ],
                "information_id": information_id,
                "persistent_state": persistent_state,
                "writes_performed": True,
            }

        event_path = create_event(
            information_id,
            revision,
            "UPDATED",
            fields.get(
                "epistemic_status",
                "UNVERIFIED",
            ),
            fields.get(
                "operational_state",
                "ACTIVE",
            ),
            "Information mise à jour dans Persistent Memory.",
            operation_id=execution[
                "operation_id"
            ],
        )

        operation_path = write_operation_record(
            execution,
            "UPDATE",
        )

        update_final_result = {
            "result": "UPDATE",
            "reason": (
                "Information mise à jour avec succès."
            ),
            "operation_id": execution[
                "operation_id"
            ],
            "information_id": information_id,
            "update": update_result,
            "persistent_state": persistent_state,
            "event": str(event_path),
            "operation_record": str(
                operation_path
            ),
            "writes_performed": True,
        }

        if not operations["INDEX"]["required"]:
            return update_final_result

        mechanisms = execution[
            "input"
        ].get(
            "mechanisms",
            {},
        )

        confirmed = mechanisms.get(
            "confirmed",
            [],
        )

        if not isinstance(
            confirmed,
            list,
        ):
            return {
                "result": "BLOCK",
                "reason": (
                    "INDEX refusé : "
                    "mechanisms.confirmed invalide."
                ),
                "operation_id": execution[
                    "operation_id"
                ],
                "information_id": information_id,
                "update": update_result,
                "writes_performed": True,
            }

        if not confirmed:
            return {
                "result": "BLOCK",
                "reason": (
                    "INDEX refusé : "
                    "aucun mécanisme confirmé."
                ),
                "operation_id": execution[
                    "operation_id"
                ],
                "information_id": information_id,
                "update": update_result,
                "writes_performed": True,
            }

        return {
            "result": "INDEX",
            "reason": (
                "UPDATE effectué. "
                "INDEX validé pour les mécanismes confirmés."
            ),
            "operation_id": execution[
                "operation_id"
            ],
            "information_id": information_id,
            "update": update_result,
            "index": {
                "status": "READY",
                "mechanisms": confirmed,
                "writes_performed": False,
            },
            "persistent_state": persistent_state,
            "event": str(event_path),
            "operation_record": str(
                operation_path
            ),
            "writes_performed": True,
        }

    return decision


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Eidolon Memory Controller"
    )

    sub = parser.add_subparsers(
        dest="command",
        required=True,
    )

    ingest_parser = sub.add_parser(
        "ingest"
    )
    ingest_parser.add_argument(
        "--content",
        required=True,
    )
    ingest_parser.add_argument(
        "--type",
        default="OBSERVATION",
    )
    ingest_parser.add_argument(
        "--mode",
        default="PROJECT",
    )
    ingest_parser.add_argument(
        "--project",
        default="Eidolon",
    )
    ingest_parser.add_argument(
        "--source-type",
        default="USER_STATEMENT",
    )
    ingest_parser.add_argument(
        "--source",
        default="manual",
    )

    validate_parser = sub.add_parser(
        "validate"
    )
    validate_parser.add_argument(
        "file",
        type=Path,
    )

    update_parser = sub.add_parser(
        "update"
    )
    update_parser.add_argument(
        "file",
        type=Path,
    )
    update_parser.add_argument(
        "--epistemic-status"
    )
    update_parser.add_argument(
        "--operational-state"
    )
    update_parser.add_argument(
        "--confidence"
    )
    update_parser.add_argument(
        "--importance"
    )
    update_parser.add_argument(
        "--reason",
        required=True,
    )
    update_parser.add_argument(
        "--event-type",
        default="UPDATED",
    )

    review_parser = sub.add_parser(
        "review"
    )
    review_parser.add_argument(
        "review",
        type=Path,
    )
    review_parser.add_argument(
        "--decision",
        required=True,
    )
    review_parser.add_argument(
        "--reason",
        required=True,
    )


    execute_parser = sub.add_parser(
        "execute",
        help=(
            "Validate an Execution Plan "
            "in validation-only mode."
        ),
    )

    execute_parser.add_argument(
        "plan",
        type=Path,
    )

    args = parser.parse_args()

    if args.command == "execute":

        try:
            data = load_execution_plan(
                args.plan
            )

            execution = validate_execution_plan(
                data
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

        result = execute_execution_plan(
            execution
        )

        print(
            json.dumps(
                result,
                ensure_ascii=False,
                indent=2,
            )
        )

        return 0

    if args.command == "ingest":
        return ingest(args)

    if args.command == "validate":
        return validate_file(
            args.file
        )

    if args.command == "update":
        return update_information(
            args.file,
            (
                args.epistemic_status.upper()
                if args.epistemic_status
                else None
            ),
            (
                args.operational_state.upper()
                if args.operational_state
                else None
            ),
            (
                args.confidence.upper()
                if args.confidence
                else None
            ),
            (
                args.importance.upper()
                if args.importance
                else None
            ),
            args.reason,
            args.event_type.upper(),
        )

    if args.command == "review":
        return resolve_review(
            args.review,
            args.decision,
            args.reason,
        )

    return 1


if __name__ == "__main__":
    sys.exit(main())

