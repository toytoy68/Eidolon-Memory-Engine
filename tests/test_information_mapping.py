from copy import deepcopy

import pytest

from core.backend.filesystem import FilesystemBackend
from core.backend.models import Memory
from core.information.mapping import information_from_memory, information_to_memory
from core.information.models import (
    Confidence, EpistemicStatus, Importance, Information, InformationType,
    OperationalState, Retention,
)
from tools.generate_scenario import generate


def example():
    return Information(
        "info-corridor", content="Deux chambres au bout du couloir.", revision=7,
        type=InformationType.OBSERVATION, epistemic_status=EpistemicStatus.CONFIRMED,
        operational_state=OperationalState.ACTIVE, confidence=Confidence.MEDIUM,
        importance=Importance.HIGH, retention=Retention.LONG_TERM,
        context={"scope": {"place_id": "house-corridor"}},
        provenance={"source_type": "DIRECT_OBSERVATION", "source": "robot-camera"},
        evidence={"supporting": ["observation-17"], "contradicting": []},
        time={"observed_at": "2026-09-30T16:00:00Z"},
        relations=[{"type": "CONCERNS", "target_id": "place-house"}],
        triggers=[{"type": "NEW_INFORMATION", "subject": "house-layout"}],
    )


def test_information_mapping_has_explicit_storage_shape_and_no_aliases():
    information = example()
    memory = information_to_memory(information)
    assert memory == Memory(
        "info-corridor", revision=7, content="Deux chambres au bout du couloir.",
        metadata={"type": "OBSERVATION", "epistemic_status": "CONFIRMED",
                  "operational_state": "ACTIVE", "confidence": "MEDIUM",
                  "importance": "HIGH", "retention": "LONG_TERM",
                  "context": {"scope": {"place_id": "house-corridor"}},
                  "triggers": [{"type": "NEW_INFORMATION", "subject": "house-layout"}]},
        provenance={"source_type": "DIRECT_OBSERVATION", "source": "robot-camera"},
        temporal={"observed_at": "2026-09-30T16:00:00Z"},
        verification={"evidence": {"supporting": ["observation-17"], "contradicting": []}},
        relations=[{"type": "CONCERNS", "target_id": "place-house"}],
    )
    assert information_from_memory(memory) == information
    memory.metadata["context"]["scope"]["place_id"] = "elsewhere"
    memory.verification["evidence"]["supporting"].append("other")
    assert information.context["scope"]["place_id"] == "house-corridor"
    assert information.evidence["supporting"] == ["observation-17"]


def test_edit_projection_preserves_storage_extensions_and_source(tmp_path):
    backend = FilesystemBackend(tmp_path / "persistent", tmp_path / "history")
    original = information_to_memory(example())
    original.metadata["legacy_revision"] = {"previous_revision": "historical-6"}
    original.metadata["qualification"] = {"version": "0.1", "nature": "SPATIAL_LAYOUT"}
    original.verification["method"] = "HUMAN_REVIEW"
    backend.store(original)
    saved = backend.get(original.information_id)
    before = deepcopy(saved)
    edited = information_from_memory(saved)
    edited.content = "Deux chambres et un bureau au bout du couloir."
    edited.context["scope"]["floor"] = "first"
    projected = information_to_memory(edited, original=saved)
    assert saved == before
    backend.update(saved.information_id, projected, previous_revision=7)
    stored = backend.get(saved.information_id)
    assert stored.revision == 8
    assert stored.content == edited.content
    assert stored.metadata["legacy_revision"] == original.metadata["legacy_revision"]
    assert stored.metadata["qualification"] == original.metadata["qualification"]
    assert stored.verification["method"] == "HUMAN_REVIEW"
    assert information_from_memory(stored).context["scope"]["floor"] == "first"


def test_mapping_preserves_all_500_migration_candidates(tmp_path):
    from core.migration.simulation import preview_legacy_information

    generate(tmp_path / "scenario")
    candidates = sorted((tmp_path / "scenario/legacy/memory/persistent").glob("*.md"))
    assert len(candidates) == 500
    for path in candidates:
        original = preview_legacy_information(path)
        projected = information_from_memory(original)
        assert information_to_memory(projected, original=original) == original


def test_projection_does_not_invent_a_missing_epistemic_status():
    memory = information_to_memory(example())
    del memory.metadata["epistemic_status"]
    with pytest.raises(KeyError, match="epistemic_status"):
        information_from_memory(memory)


def test_projection_keeps_structured_memory_outside_text_contract():
    memory = information_to_memory(example())
    memory.content = {"rooms": 5}
    with pytest.raises(TypeError, match="text"):
        information_from_memory(memory)


def test_projection_cannot_merge_extensions_from_another_identity():
    original = information_to_memory(example())
    other = example()
    other.information_id = "different"
    with pytest.raises(ValueError, match="identity"):
        information_to_memory(other, original=original)
