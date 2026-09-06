#!/usr/bin/env python3
import argparse
import re
import sys
import uuid
from datetime import datetime
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
    EVENTS_ROOT,
    REVIEWS_ROOT,
)

WORKING = WORKING_ROOT
EVENTS = EVENTS_ROOT
REVIEWS = REVIEWS_ROOT

RELATIONS = {
    "SUPPORTS", "CONTRADICTS", "DERIVED_FROM", "DEPENDS_ON",
    "SUPERSEDES", "RELATED_TO", "PART_OF", "INSTANCE_OF",
    "CAUSED_BY", "FOLLOWS",
}
EPISTEMIC = {
    "UNKNOWN", "UNVERIFIED", "CONFIRMED",
    "REFUTED", "CONFLICTED", "SUPERSEDED",
}
REVIEW_RELATIONS = {"CONTRADICTS", "SUPERSEDES"}

def read(path):
    return path.read_text(encoding="utf-8")

def information_id(path):
    m = re.search(r"^id:\s*([^\s]+)", read(path), re.MULTILINE)
    return m.group(1) if m else None

def revision(path):
    m = re.search(r"^revision:\s*(\d+)", read(path), re.MULTILINE)
    return int(m.group(1)) if m else None

def status(path):
    m = re.search(r"^epistemic_status:\s*([^\s]+)", read(path), re.MULTILINE)
    return m.group(1) if m else None

def find_information(target_id):
    for path in WORKING.glob("info-*.md"):
        if information_id(path) == target_id:
            return path
    return None

def validate_relation(source, relation, target_id):
    errors, warnings = [], []
    if relation not in RELATIONS:
        errors.append(f"relation invalide: {relation}")
        return errors, warnings
    source_id = information_id(source)
    if not source_id:
        errors.append("ID source absent")
    if not target_id:
        errors.append("ID cible absent")
    if source_id and source_id == target_id:
        errors.append("relation réflexive interdite pour cette opération")
    target = find_information(target_id)
    if target is None:
        errors.append(f"information cible introuvable: {target_id}")
        return errors, warnings
    ss, ts = status(source), status(target)
    if ss not in EPISTEMIC:
        errors.append(f"état épistémique source invalide: {ss}")
    if ts not in EPISTEMIC:
        errors.append(f"état épistémique cible invalide: {ts}")
    if relation == "CONTRADICTS" and ss == "SUPERSEDED":
        warnings.append("source SUPERSEDED : contradiction conservée pour traçabilité")
    if relation == "SUPERSEDES":
        if ss in {"REFUTED", "SUPERSEDED"}:
            warnings.append(f"source {ss} : vérifier la pertinence de la supersession")
        if ts == "SUPERSEDED":
            warnings.append("cible déjà SUPERSEDED : risque de chaîne de supersession")
        if ts == "CONFIRMED":
            warnings.append("la supersession ne signifie pas que la cible était fausse")
    return errors, warnings

def relation_exists(text, relation, target_id):
    pattern = re.compile(
        r"(?ms)^\s*-\s*type:\s*" + re.escape(relation) +
        r"\s*\n\s*target:\s*" + re.escape(target_id) + r"\s*$"
    )
    return bool(pattern.search(text))

def add_relation(text, relation, target_id):
    if relation_exists(text, relation, target_id):
        raise ValueError("relation déjà présente")
    match = re.search(r"(?ms)^relations:\s*(.*?)(?=^##\s|\Z)", text)
    if not match:
        raise ValueError("bloc relations absent")
    block = match.group(0).rstrip()
    if re.fullmatch(r"relations:\s*", block):
        new_block = f"relations:\n\n- type: {relation}\n  target: {target_id}"
    else:
        new_block = f"{block}\n- type: {relation}\n  target: {target_id}"
    return text[:match.start()] + new_block + text[match.end():]

def create_event(source_id, old_rev, new_rev, relation, target_id, review_id=None):
    now = datetime.now().astimezone()
    event_id = f"event-{now.strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:8]}"
    path = EVENTS / f"{event_id}.md"
    review_line = f"\nreview_id: {review_id}" if review_id else ""
    content = f"""event_id: {event_id}
information_id: {source_id}
revision: {new_rev}

event_type: RELATION_ADDED

state_transition:
before:
  revision: {old_rev}
after:
  revision: {new_rev}

cause:
type: RELATION_ADDED
description: "Relation {relation} ajoutée vers {target_id}."

relation:
type: {relation}
source: {source_id}
target: {target_id}
{review_line}

provenance:
source_type: SYSTEM_GENERATED
source: memory-relations
actor: eidolon
timestamp: {now.isoformat(timespec="seconds")}

validation:
mode: AUTOMATIC
status: ACCEPTED

---

# Memory Event

Ajout contrôlé d'une relation {relation}.
"""
    path.write_text(content, encoding="utf-8")
    return event_id, path

def create_review(source_id, target_id, relation):
    now = datetime.now().astimezone()
    stamp = now.strftime("%Y%m%d-%H%M%S")
    review_id = f"review-{stamp}-{uuid.uuid4().hex[:8]}"
    path = REVIEWS / f"{review_id}.md"
    content = f"""---
review_id: {review_id}
status: PENDING_REVIEW
review_type: RELATION_REVIEW
decision: null
information_id: {source_id}
target_information_id: {target_id}
relation_type: {relation}
created_at: {now.isoformat(timespec="seconds")}
resolved_at: null
resolution_event_id: null
---

# Administrative Review

Cette relation nécessite une décision humaine.

Relation proposée :

- type: {relation}
- source: {source_id}
- target: {target_id}

Le contrôleur ne doit pas forcer une transition lorsqu'un doute
persiste.

Aucune décision humaine n'a été simulée par le système.
"""
    path.write_text(content, encoding="utf-8")
    return review_id, path

def command_add(args):
    source = Path(args.source)
    if not source.is_file():
        print(f"ERREUR : fichier source introuvable : {source}")
        return 1
    errors, warnings = validate_relation(source, args.relation, args.target)
    if warnings:
        print("Avertissements:")
        for w in warnings:
            print(f"- {w}")
    if errors:
        print("Ajout de relation : REFUSÉ")
        for e in errors:
            print(f"- {e}")
        return 1
    text = read(source)
    old_rev = revision(source)
    source_id = information_id(source)
    if old_rev is None:
        print("Ajout de relation : REFUSÉ")
        print("- revision absente")
        return 1
    if relation_exists(text, args.relation, args.target):
        print("Ajout de relation : REFUSÉ")
        print("- relation déjà présente")
        return 1

    new_rev = old_rev + 1
    new_text = add_relation(text, args.relation, args.target)
    match = re.search(r"^revision:\s*\d+", new_text, re.MULTILINE)
    if not match:
        print("Ajout de relation : REFUSÉ")
        print("- champ revision introuvable")
        return 1
    new_text = new_text[:match.start()] + f"revision: {new_rev}" + new_text[match.end():]

    review_id = None
    review_path = None
    if args.review and args.relation in REVIEW_RELATIONS:
        review_id, review_path = create_review(source_id, args.target, args.relation)

    source.write_text(new_text, encoding="utf-8")
    event_id, event_path = create_event(
        source_id, old_rev, new_rev, args.relation, args.target, review_id
    )

    print(f"Relation ajoutée : {args.relation}")
    print(f"Source : {source}")
    print(f"Cible : {args.target}")
    print(f"Revision : {old_rev} -> {new_rev}")
    if review_path:
        print(f"Review créée : {review_path}")
        print(f"Review ID : {review_id}")
    print(f"Event historique : {event_path}")
    print(f"Event ID : {event_id}")
    print("Aucune transition épistémique automatique.")
    return 0

def command_review(args):
    source = Path(args.source)
    if not source.is_file():
        print(f"ERREUR : Review introuvable : {source}")
        return 1
    text = read(source)
    if "status: PENDING_REVIEW" not in text:
        print("Review : REFUSÉE")
        print("- Review non PENDING_REVIEW")
        return 1
    print(f"Review : {source}")
    print("Statut : PENDING_REVIEW")
    print("Aucune décision n'est prise par cette commande.")
    print("Résolution humaine conservée pour l'étape suivante.")
    return 0

def command_rules():
    print("Relations actives :")
    print("- CONTRADICTS")
    print("- SUPERSEDES")
    print()
    print("Review :")
    print("- --review crée une Review PENDING_REVIEW")
    print("- aucune décision automatique")
    print("- aucun changement épistémique automatique")
    print("- la Review conserve son front matter")
    print()
    print("Traçabilité :")
    print("- revision source")
    print("- Event RELATION_ADDED")
    print("- Review liée lorsque requise")
    print("- cible non modifiée")
    return 0

parser = argparse.ArgumentParser(description="Eidolon Memory Relation Engine")
sub = parser.add_subparsers(dest="command", required=True)

add = sub.add_parser("add")
add.add_argument("source")
add.add_argument("--relation", required=True)
add.add_argument("--target", required=True)
add.add_argument("--review", action="store_true")

review = sub.add_parser("review")
review.add_argument("source")

sub.add_parser("rules")
args = parser.parse_args()

if args.command == "add":
    sys.exit(command_add(args))
elif args.command == "review":
    sys.exit(command_review(args))
else:
    sys.exit(command_rules())
