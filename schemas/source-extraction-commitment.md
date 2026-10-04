# Source extraction commitment v1

Path: `memory/history/source-extractions-v1/<source_id>.json`.
Content-free, immutable identity of one extraction. This is a retained core
history family, copied with `memory/` and excluded from legacy writers.

| Field | Contract |
| --- | --- |
| `format_version` | integer 1 (not boolean) |
| `source_id` | 64 lowercase hexadecimal characters, same as filename stem |
| `source_sha256` | same original SHA-256 as `source_id` |
| `extractor` | versioned extraction driver |
| `text_sha256` | SHA-256 of UTF-8 paragraphs joined by LF |
| `paragraph_count` | positive integer, including empty paragraphs |
| `committed_at` | ISO 8601 timestamp with timezone |

Exact field set; no manuscript, paragraph, quote or accepted detail text.
At audit, identity is compared with an extraction reproduced from the validated
original. Missing original, malformed commitment, unsafe paths or mismatches
block readiness. Missing extraction with a valid reproducible promise yields
`pending_source_extraction`; only explicit extraction of that exact source can
resume it, using its committed driver. Other blockers are never bypassed.

Existing extractions with no record stay free: `uncommitted_extraction` is an
informational diagnostic, not a blocking issue. Reads/audits never engage them.
New extraction commands durably publish commitment before `extraction.json`,
under Persistent then Sources locks. Replay preserves bytes and timestamp.
No automatic recovery, implicit bulk migration or history deletion is provided.

Trust boundary: cooperative writers and retained filesystem history. Deleting
an entire commitment or changing both commitment and extraction cannot be
proven externally by this local record. Archive manifests must retain all files.
No guarantee against power loss beyond the existing flush/fsync primitives is
inferred from process-interruption tests.
