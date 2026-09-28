"""Filesystem implementation of the EventRepository contract."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

from core.persistence import serialized_write, durable_replace

from core.config import EVENTS_ROOT, ensure_directories

from .errors import EventAlreadyExists, InvalidEvent
from .models import (
    Cause,
    CauseType,
    Event,
    EventRelation,
    EventType,
    Evidence,
    Provenance,
    RelationType,
    StateTransition,
    Validation,
    ValidationMode,
    ValidationStatus,
)
from .repository import EventRepository
from .validator import validate_event


class FilesystemEventRepository(EventRepository):
    """Append-only filesystem repository for Memory Events."""

    def __init__(self, events_root: Path | None = None) -> None:
        if events_root is None:
            ensure_directories()

        self.events_root = (
            Path(events_root)
            if events_root is not None
            else EVENTS_ROOT
        )

        self.events_root.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Paths
    # ------------------------------------------------------------------

    def _validate_id(self, event_id: str) -> None:
        if not event_id:
            raise InvalidEvent("event_id is required")

        if not re.fullmatch(r"[A-Za-z0-9._-]+", event_id):
            raise InvalidEvent(
                f"invalid event_id: {event_id!r}"
            )

    def _path(self, event_id: str) -> Path:
        self._validate_id(event_id)
        return self.events_root / f"{event_id}.md"

    # ------------------------------------------------------------------
    # Serialization
    # ------------------------------------------------------------------

    @staticmethod
    def _to_dict(event: Event) -> dict[str, Any]:
        return {
            "event_id": event.event_id,
            "information_id": event.information_id,
            "thread_id": event.thread_id,
            "revision": event.revision,
            "event_type": event.event_type.value,
            "state_transition": {
                "before": event.state_transition.before,
                "after": event.state_transition.after,
            },
            "cause": (
                {
                    "type": event.cause.type.value,
                    "description": event.cause.description,
                }
                if event.cause is not None
                else None
            ),
            "evidence": {
                "supporting": event.evidence.supporting,
                "contradicting": event.evidence.contradicting,
            },
            "provenance": (
                {
                    "source_type": event.provenance.source_type,
                    "source": event.provenance.source,
                    "actor": event.provenance.actor,
                    "timestamp": event.provenance.timestamp,
                }
                if event.provenance is not None
                else None
            ),
            "validation": (
                {
                    "mode": event.validation.mode.value,
                    "status": event.validation.status.value,
                }
                if event.validation is not None
                else None
            ),
            "relations": [
                {
                    "type": relation.type.value,
                    "target": relation.target,
                }
                for relation in event.relations
            ],
        }

    @staticmethod
    def _from_dict(data: dict[str, Any]) -> Event:
        try:
            state_data = data.get("state_transition") or {}
            cause_data = data.get("cause")
            evidence_data = data.get("evidence") or {}
            provenance_data = data.get("provenance")
            validation_data = data.get("validation")
            relations_data = data.get("relations") or []

            return Event(
                event_id=data["event_id"],
                information_id=data.get("information_id"),
                thread_id=data.get("thread_id"),
                revision=int(data["revision"]),
                event_type=EventType(data["event_type"]),
                state_transition=StateTransition(
                    before=state_data.get("before") or {},
                    after=state_data.get("after") or {},
                ),
                cause=(
                    Cause(
                        type=CauseType(cause_data["type"]),
                        description=cause_data.get("description", ""),
                    )
                    if cause_data is not None
                    else None
                ),
                evidence=Evidence(
                    supporting=evidence_data.get("supporting") or [],
                    contradicting=evidence_data.get("contradicting") or [],
                ),
                provenance=(
                    Provenance(
                        source_type=provenance_data.get("source_type", ""),
                        source=provenance_data.get("source", ""),
                        actor=provenance_data.get("actor", ""),
                        timestamp=provenance_data.get("timestamp", ""),
                    )
                    if provenance_data is not None
                    else None
                ),
                validation=(
                    Validation(
                        mode=ValidationMode(validation_data["mode"]),
                        status=ValidationStatus(validation_data["status"]),
                    )
                    if validation_data is not None
                    else None
                ),
                relations=[
                    EventRelation(
                        type=RelationType(relation["type"]),
                        target=relation["target"],
                    )
                    for relation in relations_data
                ],
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise InvalidEvent("invalid serialized Event") from exc

    @classmethod
    def _serialize(cls, event: Event) -> str:
        payload = json.dumps(
            cls._to_dict(event),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )

        return (
            "# Eidolon Memory Event\n\n"
            "Version: 0.2\n\n"
            "```json\n"
            f"{payload}\n"
            "```\n"
        )

    @classmethod
    def _deserialize(cls, text: str) -> Event:
        normalized = text.replace("\r\n", "\n")
        prefix = "# Eidolon Memory Event\n\nVersion: 0.2\n\n```json\n"
        if not normalized.startswith(prefix):
            raise InvalidEvent("invalid Event header or unsupported version")
        try:
            payload = normalized[len(prefix):].lstrip()
            data, end = json.JSONDecoder().raw_decode(payload)
            if payload[end:].strip() != "```":
                raise InvalidEvent("invalid Event JSON boundary")
        except json.JSONDecodeError as exc:
            raise InvalidEvent("invalid Event JSON") from exc

        if not isinstance(data, dict):
            raise InvalidEvent("Event JSON must be an object")

        return cls._from_dict(data)

    # ------------------------------------------------------------------
    # Atomic filesystem operations
    # ------------------------------------------------------------------

    @staticmethod
    def _atomic_write(path: Path, content: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)

        with NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary_path = Path(handle.name)
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())

        durable_replace(temporary_path, path)

    # ------------------------------------------------------------------
    # Repository contract
    # ------------------------------------------------------------------

    @serialized_write("events_root")
    def save(self, event: Event) -> Event:
        self._validate_id(event.event_id)
        errors = validate_event(event)
        if errors:
            raise InvalidEvent("; ".join(errors))

        path = self._path(event.event_id)

        if path.exists():
            raise EventAlreadyExists(event.event_id)

        self._atomic_write(
            path,
            self._serialize(event),
        )

        return event

    def get(self, event_id: str) -> Event | None:
        path = self._path(event_id)

        if not path.exists():
            return None

        try:
            event = self._deserialize(path.read_text(encoding="utf-8"))
            if event.event_id != event_id:
                raise InvalidEvent("Event identity does not match filename")
            return event
        except OSError as exc:
            raise InvalidEvent(
                f"unable to read Event: {event_id}"
            ) from exc

    def list_for_target(self, target_id: str) -> list[Event]:
        if not target_id:
            raise InvalidEvent("target_id is required")

        events: list[Event] = []

        for path in sorted(self.events_root.glob("*.md")):
            try:
                event = self._deserialize(
                    path.read_text(encoding="utf-8")
                )
            except OSError as exc:
                raise InvalidEvent(
                    f"unable to read Event file: {path.name}"
                ) from exc

            if event.event_id != path.stem:
                raise InvalidEvent("Event identity does not match filename")

            if (
                event.information_id == target_id
                or event.thread_id == target_id
            ):
                events.append(event)

        return events
