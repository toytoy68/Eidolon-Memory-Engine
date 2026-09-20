# Eidolon Thread Storage Specification

Version: 0.1

---

## 1. Purpose

This document defines the canonical persistent Markdown representation of an Eidolon Thread.

A Thread is a first-class memory entity distinct from an Information object.

The Markdown representation is human-readable and acts as persistent canonical storage.

Qdrant or any other search index is not the source of truth.

---

## 2. Canonical Structure

A Thread MUST be stored using the following structure:

# Eidolon Thread Object

Version: 0.1

---

## Identity

thread_id: ...
revision: ...
title: ...
status: ...

---

## Objective

...

---

## Context

```json
{
  "key": "value"
}
```

---

## Actions

```json
[
  {
    "action_id": "...",
    "description": "...",
    "status": "PLANNED",
    "metadata": {}
  }
]
```

---

## Relations

```json
[
  {
    "type": "RELATED_TO",
    "target_id": "..."
  }
]
```

---

## Temporal

```json
{
  "created_at": "...",
  "updated_at": "...",
  "started_at": null,
  "completed_at": null
}
```

---

## Provenance

```json
{
  "created_by": "...",
  "source": "..."
}
```

---

## 3. Identity

The Identity section contains the canonical Thread identity and lifecycle state.

Required fields:

- `thread_id`
- `revision`
- `title`
- `status`

Example:

```text
## Identity

thread_id: thread-v100-watercooling
revision: 4
title: Double V100 watercooling
status: IMPLEMENTATION
```

`thread_id` MUST be unique.

`revision` MUST be an integer greater than or equal to 1.

`status` MUST contain a valid `ThreadStatus` value.

---

## 4. Objective

The Objective section contains the primary objective of the Thread.

Example:

```text
## Objective

Build and validate the custom watercooling system for the double V100 PCIe board.
```

The objective MUST be present and MUST NOT be empty.

---

## 5. Context

Context contains structured contextual information associated with the Thread.

The section MUST contain valid JSON.

The structure of `context` is intentionally extensible.

The storage layer MUST preserve unknown fields without modification.

---

## 6. Actions

Actions contains the current actionable work associated with the Thread.

The section MUST contain a JSON array.

Each action MUST contain:

- `action_id`
- `description`
- `status`
- `metadata`

`status` MUST contain a valid `ActionStatus` value.

The `action_id` MUST be unique within the Thread.

The storage layer MUST preserve action metadata.

---

## 7. Relations

Relations contains structured relationships between the Thread and other memory entities.

The section MUST contain a JSON array.

Relation structure is intentionally extensible.

The storage layer MUST preserve unknown relation fields.

---

## 8. Temporal

Temporal contains Thread lifecycle timestamps.

Required fields:

- `created_at`
- `updated_at`
- `started_at`
- `completed_at`

`started_at` MAY be null.

`completed_at` MUST be null unless the Thread has reached `COMPLETED`.

Timestamps MUST use ISO-8601 representation.

---

## 9. Provenance

Provenance contains information describing the origin and history context of the Thread.

The section MUST contain valid JSON.

The structure is intentionally extensible.

The storage layer MUST preserve unknown provenance fields.

---

## 10. Versioning

The storage format version is declared at the beginning of the document:

```text
Version: 0.1
```

The format version describes the Markdown storage representation.

It is distinct from the Thread `revision`.

For example:

```text
Version: 0.1
revision: 7
```

means:

- storage format version: `0.1`
- current Thread revision: `7`

---

## 11. Revision Principle

Every persistent modification of a Thread MUST increment its revision.

For example:

```text
revision: 3
```

becomes:

```text
revision: 4
```

The revision represents the current state version of the Thread.

Thread events reference the resulting revision.

The current Markdown representation is the canonical current state.

---

## 12. Canonical Storage Location

Threads MUST be stored separately from Information objects.

Recommended structure:

```text
persistent/
├── <information_id>.md
└── threads/
    ├── <thread_id>.md
    └── ...
```

Information objects remain directly under the persistent root.

Threads are stored under the dedicated `threads/` directory.

---

## 13. Identifier Rules

A `thread_id` MUST contain only:

```text
A-Z
a-z
0-9
.
_
-
```

The identifier MUST NOT contain:

- `/`
- `\`
- whitespace
- `..`
- path traversal components

The storage implementation MUST validate the identifier before constructing a filesystem path.

---

## 14. Atomic Persistence

Thread writes MUST be atomic.

The storage implementation MUST:

1. create a temporary file in the destination directory;
2. write the complete Thread representation;
3. flush the file;
4. synchronize the file descriptor;
5. atomically replace the destination file.

A partially written Thread MUST never become the canonical persistent representation.

---

## 15. Read / Write Principle

The storage layer MUST provide at least:

- `create`
- `get`
- `exists`
- `update`
- `delete`
- `list`

The storage layer is responsible for serialization and persistence.

The ThreadManager remains responsible for Thread domain rules.

The query layer remains responsible for expressing read operations.

---

## 16. Separation of Responsibilities

The architecture MUST preserve the following separation:

```text
ThreadQuery
    ↓
ThreadManager
    ↓
Thread Storage
    ↓
Canonical Markdown
```

Responsibilities:

### ThreadQuery

Defines what is requested.

### ThreadManager

Applies Thread domain rules and executes queries against loaded Thread objects.

### Thread Storage

Loads and persists Thread objects.

### Markdown

Represents the canonical persistent state.

### Qdrant

Provides a reconstructible search/index layer and is never the canonical source of Thread state.

---

## 17. Compatibility

This storage format MUST NOT modify the existing Information storage format.

Information objects and Thread objects remain separate memory entity types.

Existing Information persistence MUST continue to function unchanged.
