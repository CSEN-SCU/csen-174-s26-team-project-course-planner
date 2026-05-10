# Topic statement

Each user’s textual notes are persisted in a dedicated human-readable Markdown file; embeddings are computed from each entry’s text so later queries can rank the closest prior notes for that same user only.

# Scope

- Covers write, similarity search, listing all rows for one user, single-row delete, bulk delete, and vector construction for a string.
- Excludes how retrieved snippets are redacted or injected into prompts (handled upstream).

# Data contracts

- **Storage:** one UTF-8 Markdown file per user under ``COURSE_PLANNER_MEMORY_DIR`` (default ``<app>/data/memory/<user_id>.md``), containing a short preamble plus delimited blocks; each block opens with a single-line JSON header after an opening marker and closes with an end marker.
- **Memory row:** numeric id, owning user id, kind enum drawn from a fixed three-string allow-list, non-empty body text, optional JSON metadata object, creation timestamp (ISO string in the JSON header).
- **Vector:** sequence of floats whose length matches the global embedding dimension constant; computed on demand for ranking (not stored in the file).
- **Retrieve result row:** id, user id, kind, content, meta JSON string or null, created time, numeric distance score ascending with relevance (cosine-style distance derived from query vs entry embeddings).
- **Kinds allowed:** preference, plan outcome, note (any other kind rejected at write time).

# Behaviors (execution order)

1. Validate user id is a positive integer before any filesystem touch; null, non-numeric, or non-positive values raise immediately.
2. On write, reject empty trimmed content and reject disallowed kind strings.
3. Embed the trimmed content: if no API key environment variable is set, produce a deterministic pseudo-vector derived from repeated hashing so length always matches the schema.
4. When an API key is set, call the vendor embedding endpoint; on empty response, dimension mismatch after pad/truncate logic, or any exception, fall back to the same deterministic pseudo-vector.
5. Append a new delimited block to the user’s Markdown file with a monotonic numeric id, the user id, kind, created timestamp, optional meta JSON, and body text; write atomically (temp file then replace).
6. On retrieve, reject empty trimmed query with an empty result list; zero or negative requested count returns an empty list.
7. Embed the query string with the same rules as writes; embed each stored entry’s body; rank entries for that user only by ascending distance (lower is closer), return up to the requested count.
8. On list, parse every block belonging to the user, return each as a dict ordered newest numeric id first, with no distance field.
9. On single delete, rewrite the file without the block whose id matches only when the owning user id matches; return whether a block was removed.
10. On bulk delete, remove all blocks for the user in one atomic rewrite; return how many blocks were deleted.

# Error paths

- Invalid user id, kind, or empty content on write raises a value error before persistence.
- Malformed delimiters in a hand-edited file may cause blocks to be skipped by the parser until repaired.
- Filesystem errors propagate to the caller on write, retrieve, list, and delete paths except where callers intentionally swallow them.
