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
- [x] Curriculum PDF gap analysis in the signed-in sidebar (`run_requirement_agent`), populating `missing_details` for Step 2 and showing last-run summary tables.
- [x] Shared lazy `agents/gemini_client.get_genai_client` so PDF gap analysis and schedule generation both require `GEMINI_API_KEY` or `GOOGLE_API_KEY` (and honor `GEMINI_MODEL`).

## Todo
- [x] Show planning-result heuristic warnings (high unit load, dense schedule) in the main plan area, Summary column, and above Step 3 when a schedule preview exists (`main.py` reads `planning_result["warnings"]`).
- [x] Thursday in meeting patterns: ``Th`` or single-letter ``R`` maps to the Thursday column; day run ``MTTh`` tokenizes with ``Th`` before bare ``T`` (`utils/meeting_pattern_parse.py`, `main.py` `day_map`).
- [x] Time tail after ``|``: first and last ``H:MM AM/PM`` tokens define start/end so extra hyphens or filler segments do not break parsing (`utils/meeting_pattern_parse.py`; tests in `tests/test_meeting_pattern_parse.py`).
- [x] Memory retrieval query uses stripped preference text so surrounding whitespace does not change embedding retrieval (`orchestrator.plan_for_user`; test `test_preference_leading_trailing_whitespace_does_not_change_retrieve_query`).
- [x] Removed unused `utils/pdf_reader.py` (no spec consumer; PDF bytes go straight to Gemini).
- [ ] LOW: Reconcile the session-flow specification wording for how the gap list is built so it matches the gap-rows specification (per-row status filter versus ambiguous “not satisfied” wording).
- [ ] HIGH: Replace text input in chatbot with speech-to-text voice input so users can speak preferences and follow-up questions instead of typing.

- [ ] HIGH: Replace SQLite memory storage with per-user structured Markdown files (one file per user) containing sections for preferences, past plans, and conversation history; each file is human-readable and editable.

- [ ] HIGH: Add memory summarization step that condenses older memory entries into a compact summary before they exceed a size threshold, preventing unbounded memory growth across sessions.

- [ ] HIGH: Change UI color scheme to SCU brand colors (primary red #8B0000 / #C8102E) across all components including sidebar, buttons, headers, and accents.

- [ ] MED: Under each recommended course card, display a ranked list of all available instructors for that course with their RateMyProfessor rating, difficulty score, and would-take-again percentage sorted by rating descending.

- [ ] MED: Make the weekly calendar interactive — clicking a course block removes it from the schedule and triggers a replacement recommendation that satisfies remaining degree requirements and fits the vacated time slot.

- [ ] LOW: When suggesting replacement courses after a removal, show which specific degree requirement each suggestion fulfills and confirm it has an available section in the same time window.