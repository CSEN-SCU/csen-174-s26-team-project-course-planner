# Topic statement

A remote JSON-schema-constrained model proposes next-term courses from a gap list plus a student-authored message, optionally revising an earlier plan, then post-processes lab pairings plus recomputed unit totals.

# Scope

- Covers prompt assembly, memory snippet injection with a character ceiling, follow-up versus first-turn instructions, transient error retries with alternate model ids, JSON extraction, lab co-requisite augmentation for selected subjects, warning heuristics, and metadata stamping.
- Excludes professor enrichment and workbook time alignment.

# Data contracts

- **Input gap objects:** expected to carry course, category, and units fields usable by downstream pairing logic.
- **Output object fields:** `recommended` array of items with course, category, units, reason, and an empty alternatives array added if missing; integer `total_units`; string `advice`; optional string `assistant_reply`; `meta` with provider label, resolved model name, whether a fallback model differed from the primary environment override, and a random request id; `warnings` array of small objects with code and human message when heuristics fire.
- **Schema requirements from host:** recommended list, total units, and advice are mandatory keys in the remote schema; assistant reply is optional in schema but instructed in text.
- **Environment knobs:** primary model id, per-attempt retry sleeps for capacity-like errors, maximum characters of injected memory context.

# Behaviors (execution order)

1. Refuse to run when the API key environment pair is entirely unset, raising a clear configuration error before any network call.
2. Lazily create a single client instance bound to that key for reuse.
3. Build a memory prefix block: when snippets exist, prepend a banner explaining precedence, then bullet lines until adding another line would exceed the character budget.
4. When a prior plan dict with a non-empty recommended array is supplied, build a second banner block listing up to eight prior courses with units, categories, reasons, plus prior total units; this activates follow-up specific instructions in the user prompt.
5. Concatenate banners, serialized gap JSON, the current student message, and conditional follow-up rules (diff language versus first-turn summary language).
6. Attach a long system instruction covering catalog code style, JSON-only output, precedence between memory and current ask, arithmetic consistency between unit sum and stated total, lab same-quarter pairing expectations, senior design sequencing guidance, and assistant-reply self-consistency rules.
7. Attempt generation with the configured primary model up to three attempts; on each failure, if the error text looks like transient overload, backoff sleep then retry, else stop retrying that model early.
8. If all attempts for a model fail, repeat the loop for each fallback model name deduplicated with the primary until one attempt returns a response object.
9. If every attempt across all models fails, raise bundling the last few error strings.
10. Take the first non-empty text body; if empty, raise.
11. Strip optional markdown code fences then parse JSON; on parse failure, raise advising shorter inputs.
12. Copy the recommended array; for each item whose subject appears in a fixed STEM set, if the catalog number looks like a lab suffix or lacks it while a partner exists in the gap map, synthesize a partner row pulling category and units from the gap map with a default unit guess when non-numeric, append partners not already present, then recompute total units as the integer sum of item unit fields ignoring bad casts.
13. Attach warnings when total units reaches a high-load threshold or when recommended count reaches a density threshold.
14. Return the augmented dict.

# Error paths

- Missing API keys before first client creation.
- Exhausted retries across models with a composite error value.
- Empty model payload.
- JSON parse errors after stripping fences.
- Non-transient HTTP or client errors break out of the retry loop for that model immediately after logging the failure string internally.
