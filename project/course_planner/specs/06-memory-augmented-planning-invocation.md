# Topic statement

The end-to-end planning entrypoint composes a retrieval query from preference text plus short gap-code hints, pulls recent personal notes, scrubs sensitive-looking fragments, invokes schedule generation, then best-effort persists a compact textual summary of the outcome.

# Scope

- Covers retrieval budget, redaction rules, the text template written back to memory, and silent failure policy around persistence.
- Excludes professor lookups, calendar layout, and UI session keys.

# Data contracts

- **Inputs:** integer user id; list of gap objects (each may contain course, category, units); free-text preference string; optional prior plan object shaped like the generator output (recommended array, total units, advice, assistant reply).
- **Outputs:** the same structure returned by the schedule generator, unmodified, including any meta and warning arrays attached there.
- **Retrieval query string:** concatenation of the trimmed preference with a comma-separated list of up to five course strings from gap objects, prefixed by a literal gap label.
- **Snippet budget:** maximum number of memory rows configurable by environment, defaulting to four.
- **Redaction placeholders:** email-shaped substrings, nine-digit identifier patterns with optional internal dashes, and long digit runs resembling phone numbers are replaced with neutral tokens inside snippets only.

# Behaviors (execution order)

1. Reject a null user id with a value error.
2. Build the retrieval query from preference text and the first few gap course fields.
3. Attempt memory retrieval for that user and query inside a broad catch; any failure yields an empty snippet list without surfacing.
4. Deduplicate retrieved bodies by exact string equality after trimming while preserving first-seen order.
5. Apply redaction replacements to each kept snippet.
6. Invoke schedule generation with the gap list, preference text, snippet list, and prior plan object when provided.
7. Build a short multi-line summary string encoding trimmed preference (truncated with ellipsis when very long), up to five gap course codes, recommended course codes from the fresh plan, and the plan’s total units field.
8. Attempt to append a new memory row of kind plan-outcome with that summary and small JSON metadata holding total units and recommended count; swallow any exception so the user still receives the plan dict.
9. Return the plan dict to the caller.

# Error paths

- Null user id raises before retrieval or generation.
- Retrieval failures are treated as zero snippets (no user-visible error from this layer).
- Generation failures propagate unchanged to the caller.
- Memory write failures are swallowed entirely; the caller cannot distinguish success from write failure without inspecting the store.
