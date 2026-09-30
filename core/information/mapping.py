"""Explicit textual Information projection over the existing Memory contract.

No writes, revision increment or historical defaults are performed here.
Pass the original Memory when projecting an edit back to preserve extensions.
"""

from copy import deepcopy

from core.backend.models import Memory
from .models import (
    Confidence, EpistemicStatus, Importance, Information, InformationType,
    OperationalState, Retention,
)


ENUM_FIELDS = {
    "type": InformationType,
    "epistemic_status": EpistemicStatus,
    "operational_state": OperationalState,
    "confidence": Confidence,
    "importance": Importance,
    "retention": Retention,
}


def information_from_memory(memory: Memory) -> Information:
    """Project explicitly labelled textual storage, without inventing labels.

    Missing enum fields raise KeyError; unsupported labels raise ValueError.
    Unclassified historical records require an explicit migration decision.
    """
    if not isinstance(memory.content, str):
        raise TypeError("Information projection requires text content")
    return Information(
        information_id=memory.information_id, revision=memory.revision,
        content=memory.content,
        **{name: enum(memory.metadata[name]) for name, enum in ENUM_FIELDS.items()},
        context=deepcopy(memory.metadata.get("context", {})),
        triggers=deepcopy(memory.metadata.get("triggers", [])),
        provenance=deepcopy(memory.provenance), time=deepcopy(memory.temporal),
        evidence=deepcopy(memory.verification.get(
            "evidence", {"supporting": [], "contradicting": []})),
        relations=deepcopy(memory.relations),
    )


def information_to_memory(information: Information, *, original: Memory | None = None) -> Memory:
    """Map a new object, or merge a projection back into its original storage.

    The original is not mutated. Unknown metadata and verification fields stay
    intact; omitted optional fields stay omitted when the projection is empty.
    Revision is carried verbatim, leaving allocation to a coordinated writer.
    """
    if not isinstance(information.content, str):
        raise TypeError("Information projection requires text content")
    if original is not None and original.information_id != information.information_id:
        raise ValueError("original Memory identity differs from Information identity")
    memory = deepcopy(original) if original is not None else Memory(information.information_id)
    memory.revision = information.revision
    memory.content = information.content
    memory.metadata.update({
        name: enum(getattr(information, name)).value for name, enum in ENUM_FIELDS.items()
    })
    for name, empty in (("context", {}), ("triggers", [])):
        value = getattr(information, name)
        if original is None or name in memory.metadata or value != empty:
            memory.metadata[name] = deepcopy(value)
    evidence = information.evidence
    if (original is None or "evidence" in memory.verification
            or evidence != {"supporting": [], "contradicting": []}):
        memory.verification["evidence"] = deepcopy(evidence)
    memory.provenance = deepcopy(information.provenance)
    memory.temporal = deepcopy(information.time)
    memory.relations = deepcopy(information.relations)
    return memory
