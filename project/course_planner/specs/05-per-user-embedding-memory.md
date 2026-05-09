# Topic statement

Each user’s textual notes are persisted with a fixed-length vector so later queries can rank the closest prior notes for that same user only.

# Scope

- Covers write, similarity search, listing all rows for one user, single-row delete, bulk delete, and vector construction for a string.
- Excludes how retrieved snippets are redacted or injected into prompts (handled upstream).

# Data contracts

- **Memory row:** numeric id, owning user id foreign key, kind enum drawn from a fixed three-string allow-list, non-empty body text, optional JSON metadata blob, creation timestamp.
- **Vector:** sequence of floats whose length matches the global embedding dimension constant; stored packed as binary for the similarity engine.
- **Retrieve result row:** id, user id, kind, content, meta JSON string or null, created time, numeric distance score ascending with relevance.
- **Kinds allowed:** preference, plan outcome, note (any other kind rejected at write time).

# Behaviors (execution order)

1. Validate user id is a positive integer before any database touch; null, non-numeric, or non-positive values raise immediately.
2. On write, reject empty trimmed content and reject disallowed kind strings.
3. Embed the trimmed content: if no API key environment variable is set, produce a deterministic pseudo-vector derived from repeated hashing so length always matches the schema.
4. When an API key is set, call the vendor embedding endpoint; on empty response, dimension mismatch after pad/truncate logic, or any exception, fall back to the same deterministic pseudo-vector.
5. Insert the textual row then insert a parallel vector row keyed by the same numeric id; commit as one transaction.
6. On retrieve, reject empty trimmed query with an empty result list; zero or negative requested count returns an empty list.
7. Embed the query string with the same rules as writes, pack to binary, then run a similarity query joining vector storage to textual rows filtered strictly by the requesting user id, ordered by ascending distance, limited to the requested count after over-fetching a bounded multiple for filtering.
8. On list, return every row for the user ordered newest id first with no vector fields.
9. On single delete, remove the textual row only when id and user match; if removed, delete the paired vector row explicitly because cascade rules do not cover the virtual vector table, then commit.
10. On bulk delete, collect all ids for the user, delete textual rows and vector rows in one batch, return how many ids were deleted.

# Error paths

- Invalid user id, kind, or empty content on write raises a value error before persistence.
- Vector packing raises if the float sequence length does not match the configured dimension (should not occur when using the module’s own embed path).
- Database errors propagate to the caller on write, retrieve, list, and delete paths except where callers intentionally swallow them.
