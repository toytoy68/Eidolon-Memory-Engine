# ==========================================================
# Projet      : Eidolon Memory Engine
# Organisation: Eidolon Core Technologies (ECT)
# Fichier     : tools/generate_scenario.py
# Description : Reproducible anonymous core and legacy scenario for migration and retrieval.
# Standard    : Eidolon Presentation Standard v1
# ==========================================================

"""Reproducible anonymous core and legacy scenario for migration and retrieval."""

from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
import random

import yaml

from core.backend.filesystem import FilesystemBackend
from core.backend.models import Memory
from core.threads.models import Thread, ThreadStatus
from core.threads.storage import ThreadStorage


TOPICS = (
    "refroidissement GPU V100", "réseau fibre SFP", "stockage RAIDZ1",
    "robotique moteur", "chauffage pompe chaleur", "journaux reprise",
    "mémoire épistémique", "capteur caméra", "alimentation UPS",
    "index recherche",
)
STATUSES = ("CONFIRMED", "UNVERIFIED", "REFUTED", "CONFLICTED", "SUPERSEDED")


def _legacy(path: Path, header: dict, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("---\n" + yaml.safe_dump(header, allow_unicode=True, sort_keys=False)
                    + "---\n" + body, encoding="utf-8")


def generate(output: Path, *, seed: int = 70427, count: int = 500) -> dict:
    """Write only beneath an empty explicit output path, with no real data."""
    output = Path(output)
    if output.exists() and any(output.iterdir()):
        raise ValueError("output directory must be empty")
    output.mkdir(parents=True, exist_ok=True)
    randomizer = random.Random(seed)
    core = output / "core"
    legacy = output / "legacy"
    backend = FilesystemBackend(core / "memory/persistent", core / "memory/history")
    statuses = {value: 0 for value in STATUSES}
    for index in range(count):
        identifier = f"info-fixture-{index:04d}"
        topic = TOPICS[index % len(TOPICS)]
        status = STATUSES[(index // len(TOPICS)) % len(STATUSES)]
        statuses[status] += 1
        value = randomizer.randrange(10, 90)
        body = (f"Observation anonyme {identifier} : {topic}. Module série {index // 10:02d}, "
                f"mesure simulée {value} unités, contrôle périodique.\n")
        metadata = {"type": "OBSERVATION", "epistemic_status": status,
                    "operational_state": "ACTIVE", "confidence": "MEDIUM",
                    "importance": "NORMAL", "retention": "NORMAL",
                    "context": {"topic": topic}}
        revision = 1
        if index % 50 == 0:
            metadata["legacy_revision"] = {"shape": "structured", "is_revision": False}
            revision = {"number": 1, "is_revision": False}
        relations = ([{"type": "RELATED_TO", "target_id": f"info-fixture-{index-1:04d}"}]
                     if index > 0 and index % 5 == 0 else [])
        provenance = {"source": "anonymous-generator", "seed": seed}
        temporal = {"valid_from": "2026-01-01T00:00:00Z"}
        evidence = {"supporting": [f"sample-{index // 10:02d}"]}
        backend.store(Memory(identifier, content=body, metadata=metadata,
                             provenance=provenance, temporal=temporal,
                             verification={"evidence": evidence}, relations=relations))
        header = {"id": identifier, "revision": revision, "type": "OBSERVATION",
                  "epistemic_status": status, "operational_state": "ACTIVE",
                  "confidence": "MEDIUM", "importance": "NORMAL",
                  "context": {"topic": topic}, "provenance": provenance,
                  "evidence": evidence, "time": temporal, "relations": relations,
                  "retention": "NORMAL"}
        _legacy(legacy / "memory/persistent" / f"{identifier}.md", header, body)

    threads = ThreadStorage(core / "memory/persistent")
    for index in range(12):
        threads.create(Thread(f"thread-fixture-{index:02d}", f"Suivi {TOPICS[index % 10]}",
                              "Examiner les mesures anonymes", status=ThreadStatus.PROPOSED,
                              created_at="2026-01-01T00:00:00Z", updated_at="2026-01-01T00:00:00Z",
                              relations=[{"type": "CONCERNS", "target_id": f"info-fixture-{index:04d}"}]))

    deleted = f"info-fixture-{count-1:04d}"
    applying = f"info-fixture-{count-2:04d}"
    pending = f"info-fixture-{count-3:04d}"
    for identifier in (deleted, applying, pending):
        backend.delete_request(identifier, "fixture", "synthetic lifecycle", 1,
                               f"delete-{identifier}")
    backend.approve_delete(deleted, f"delete-{deleted}")
    receipt = backend.pending_delete_root / f"{applying}.json"
    record = json.loads(receipt.read_text(encoding="utf-8"))
    record["status"] = "APPLYING_DELETE"
    record["content_sha256"] = sha256(backend._path(applying).read_bytes()).hexdigest()
    receipt.write_text(json.dumps(record, sort_keys=True) + "\n", encoding="utf-8")

    for index in range(6):
        identifier = f"info-fixture-{index:04d}"
        _legacy(legacy / "memory/history/events" / f"event-{index:02d}.md",
                {"event_id": f"event-{index:02d}", "event_type": "CREATED",
                 "information_id": identifier}, "Historical event retained.\n")
        _legacy(legacy / "memory/history/reviews" / f"review-{index:02d}.md",
                {"review_id": f"review-{index:02d}", "status": "RESOLVED",
                 "information_id": identifier}, "Historical review retained.\n")
    _legacy(legacy / "memory/working/working-fixture-01.md",
            {"id": "working-fixture-01", "revision": 1, "type": "OBSERVATION",
             "epistemic_status": "UNVERIFIED", "operational_state": "ACTIVE",
             "confidence": "LOW", "importance": "NORMAL", "context": {"topic": "draft"},
             "provenance": {"source": "anonymous-generator"}, "evidence": {},
             "time": {}, "relations": [], "retention": "NORMAL"},
            "Draft awaiting a historical decision.\n")
    for index in range(2):
        receipt = {"operation_id": f"legacy-op-{index:02d}",
                   "execution_plan_hash": sha256(f"synthetic-plan-{index}".encode()).hexdigest(),
                   "information_id": f"info-fixture-{index:04d}",
                   "result": {"stored": True}, "status": "EXECUTED",
                   "timestamp": "2026-01-01T00:00:00Z"}
        path = legacy / "memory/history/operations" / f"legacy-op-{index:02d}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(receipt, ensure_ascii=False, sort_keys=True) + "\n",
                        encoding="utf-8")
    result = {"seed": seed, "information": count - 1, "legacy_information": count,
              "threads": 12, "pending_deletions": 2, "completed_deletions": 1,
              "refuted": statuses["REFUTED"], "conflicted": statuses["CONFLICTED"],
              "historical_events": 6, "historical_reviews": 6,
              "historical_operations": 2, "working_information": 1}
    (output / "scenario.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n",
                                          encoding="utf-8")
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=70427)
    parser.add_argument("--count", type=int, default=500)
    args = parser.parse_args(argv)
    print(json.dumps(generate(args.output, seed=args.seed, count=args.count),
                     ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
