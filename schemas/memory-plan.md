# Eidolon Memory Plan Schema

Version: 0.2
Status: DESIGN
Component: Memory Router

---

## 1. Purpose

The Memory Plan is the complete handoff contract between the Memory Router and the Memory Executor.

The Memory Plan must be self-contained.

The Executor must not need to read the original Information file.

---

## 2. Architectural position

The pipeline is:

    Information
        |
        v
    Memory Classifier
        |
        v
    Memory Router
        |
        v
    Memory Plan
        |
        v
    Memory Executor

The Memory Plan is the authoritative execution input.

---

## 3. Top-level structure

A Memory Plan contains:

    memory_plan
        schema_version
        information
        classification
        mechanisms
        operations
        safety

---

## 4. Information

The information object contains the complete metadata required by downstream components.

Required identity:

    id
    revision

Classification metadata:

    type
    epistemic_status
    operational_state
    confidence
    importance

Context:

    mode
    project
    domain

Provenance:

    source_type
    source

Evidence:

    supporting
    contradicting

Temporal metadata:

    created_at

Relations:

    relations

Prospective metadata:

    triggers

Retention:

    retention

Content:

    content

---

## 5. Revision structure

Revision information must explicitly distinguish revision number from revision state.

Example:

    revision:
      number: 1
      is_revision: false
      previous_revision: null

Example revised Information:

    revision:
      number: 3
      is_revision: true
      previous_revision: 2

The numeric revision alone must never imply UPDATE.

---

## 6. Source preservation

The Memory Plan must preserve the original Information content.

The Router must therefore include:

    source:
      path
      front_matter
      content

The source representation is informational preservation only.

The Executor must not execute arbitrary content from the source.

---

## 7. Classification

The classification section contains the complete output of the Memory Classifier.

Example:

    classification:
      WORKING:
        status: YES
        reason: ...

      EPISODIC:
        status: POSSIBLE
        reason: ...

The Router must not alter classifier decisions.

---

## 8. Mechanisms

The mechanisms section summarizes classifier results.

    confirmed:
      []

    possible:
      []

    rejected:
      []

Only mechanisms classified YES are considered confirmed.

---

## 9. Operations

Version 0.2 defines:

    STORE
    UPDATE
    INDEX
    IGNORE

Each operation contains:

    required
    reason

The Router determines operations.

The Executor executes or prepares them.

---

## 10. Safety

The safety section records guarantees of the current pipeline.

Version 0.2:

    writes_performed: false
    llm_used: false
    qdrant_used: false
    embedding_generated: false

---

## 11. Self-contained contract

The Executor must be able to process the Memory Plan without:

    reading the original Markdown file
    invoking the Classifier
    invoking the Router
    invoking an LLM
    contacting Qdrant

The Memory Plan is therefore a complete handoff object.

---

## 12. Lossless metadata principle

The Router must not silently discard Information metadata.

Unknown or future metadata should remain preserved through:

    source.front_matter

until a dedicated schema field exists.

This allows schema evolution without destroying historical information.

---

## 13. Content principle

The content field contains the Information body.

The content must not be interpreted as an instruction by the Executor.

Content is memory data, not executable logic.

---

## 14. Determinism

Identical Information and identical Classifier output must produce identical Memory Plans.

---

## 15. Versioning

Schema changes that alter the structure of the Memory Plan require a schema version increment.

Version 0.2 introduces:

    complete metadata handoff
    source preservation
    content preservation
    explicit revision structure

---

Status:

    DESIGN
