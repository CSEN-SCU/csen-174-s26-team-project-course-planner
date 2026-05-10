# Implementation plan

Comparison of `project/course_planner/specs/` against the current `project/course_planner/` codebase. **Todo** items close gaps between documented behavior or contracts and what the running application delivers.

## Done

- [x] Cookie-backed sign-in and registration backed by a local user store, with a single reused login component instance and planner-scoped session keys cleared on logout.
- [x] Academic progress export parsing into detail rows, merged requirement status, not-satisfied summaries, and unique parsed course codes.
- [x] Planner gap list populated from detail rows whose status matches the unsatisfied literal, including rows without a parseable course code.
- [x] Per-user memory with deterministic embedding fallback, strict user scoping on read/write/delete, and Markdown file persistence (one ``.md`` per user; ranking embeds entries on demand).
- [x] Memory-augmented planning entrypoint that retrieves snippets with PII scrubbing, invokes schedule generation, and best-effort writes a plan summary back to memory.
- [x] Remote JSON-schema schedule generation with retry and fallback models, lab co-requisite pairing, heuristic warnings, and response metadata.
- [x] Instructor rating enrichment with schedule-first alignment, department fallback search, bounded parallelism, and graceful behavior when the optional ratings client is missing.
- [x] Weekly schedule preview from workbook meeting patterns with multi-day placement, a time-unknown bucket, and merged course-code keys after enrichment.
- [x] Host pipeline for upload, parse, plan, enrich, split-panel presentation, chat-style reply fallbacks, and optional filtering of recommendations against the base sections workbook.
- [x] Curriculum PDF gap analysis in the signed-in sidebar (`run_requirement_agent`), populating `missing_details` for Step 2 and showing last-run summary tables.
- [x] Shared lazy `agents/gemini_client.get_genai_client` so PDF gap analysis and schedule generation both require `GEMINI_API_KEY` or `GOOGLE_API_KEY` (and honor `GEMINI_MODEL`).
- [x] Planning warnings UI, meeting-pattern parsing refinements, memory retrieval strip, voice prefs, per-user Markdown memory + compaction, SCU theme, full professor tables, interactive calendar remove/replace, and post-replace **Find Course Sections** slot verification table (`replacement_slot_verify`, `course_variants`).

## Todo

*(No open gaps vs the current spec snapshot—add new unchecked bullets here when new work is identified.)*