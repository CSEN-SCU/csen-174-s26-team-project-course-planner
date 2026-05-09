# Implementation plan

Comparison of `project/course_planner/specs/` against the current `project/course_planner/` codebase. **Todo** items close gaps between documented behavior or contracts and what the running application delivers.

## Done

- [x] Cookie-backed sign-in and registration backed by a local user store, with a single reused login component instance and planner-scoped session keys cleared on logout.
- [x] Academic progress export parsing into detail rows, merged requirement status, not-satisfied summaries, and unique parsed course codes.
- [x] Planner gap list populated from detail rows whose status matches the unsatisfied literal, including rows without a parseable course code.
- [x] Per-user embedding memory with deterministic fallback vectors, strict user scoping on read/write/delete, and vector row cleanup on delete.
- [x] Memory-augmented planning entrypoint that retrieves snippets with PII scrubbing, invokes schedule generation, and best-effort writes a plan summary back to memory.
- [x] Remote JSON-schema schedule generation with retry and fallback models, lab co-requisite pairing, heuristic warnings, and response metadata.
- [x] Instructor rating enrichment with schedule-first alignment, department fallback search, bounded parallelism, and graceful behavior when the optional ratings client is missing.
- [x] Weekly schedule preview from workbook meeting patterns with multi-day placement, a time-unknown bucket, and merged course-code keys after enrichment.
- [x] Host pipeline for upload, parse, plan, enrich, split-panel presentation, chat-style reply fallbacks, and optional filtering of recommendations against the base sections workbook.

## Todo

- [ ] HIGH: Offer curriculum PDF gap analysis inside the same signed-in planner flow so the callable described in the PDF gap specification is reachable without separate tooling.
- [ ] HIGH: Make the PDF gap analysis path use the same explicit hosted-model key configuration expectation as schedule generation so both flows behave consistently in typical deployments.
- [ ] MED: Show the planning result warning messages (high unit load, dense schedule) wherever the generated plan is presented so users see guidance the generator already attaches.
- [ ] MED: Place courses whose meeting patterns use a single-letter Thursday token into the Thursday column instead of only treating the two-letter Thursday token as Thursday.
- [ ] MED: Parse meeting time ranges reliably when the time portion contains extra hyphen characters beyond the start–end delimiter.
- [ ] LOW: Ensure leading and trailing whitespace on the current preference text does not change which prior notes are retrieved for context.
- [ ] LOW: Resolve undocumented PDF helper code so every file under the package either has a specification topic or is removed from the shipped tree.
- [ ] LOW: Reconcile the session-flow specification wording for how the gap list is built so it matches the gap-rows specification (per-row status filter versus ambiguous “not satisfied” wording).
