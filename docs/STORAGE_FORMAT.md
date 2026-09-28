# Storage format 0.2

New Thread and backend Information writes use UTF-8 Markdown with a versioned
header and one JSON code block. The complete object is encoded as JSON: titles,
Markdown content, whitespace, embedded code fences and nested metadata survive
round trips without delimiter collisions. Files open in ordinary Markdown editors,
including Obsidian, but are structured engine documents, not a note-editing UI.

Readers continue to support the old core Markdown format 0.1. No existing file
is rewritten by deployment or by reading. Updating an object writes version 0.2.
Unknown versions fail explicitly. Historical CLI YAML/front-matter documents are
not the core format 0.1 and are not automatically migrated by this release.

Older engine versions cannot read new 0.2 documents. Before rollback, preserve
new data and use a compatible reader or an explicitly reviewed conversion. A Git
rollback alone is insufficient once new documents have been written.

Do not manually edit operation journals or their persisted Thread snapshots:
their hashes are intentional recovery integrity checks. A future editable notes
view should submit changes through the revision-controlled service.

# Thread queries

`include_completed` and `include_cancelled` extend LIST_OPEN_THREADS and
LIST_OPEN_ACTIONS to those parent Thread states. LIST_THREADS and explicit
status queries retain their own scope. Action filtering still applies after
parent selection. Actions follow the requested parent Thread ordering before
pagination; within a Thread they retain their stored order.

ISO dates and timestamps are compared as UTC instants. Legacy timestamps with
no offset are interpreted as UTC. Empty sort timestamps precede real timestamps
in ascending order. Invalid supplied date filters are rejected.
