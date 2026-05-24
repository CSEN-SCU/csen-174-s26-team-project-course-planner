# AGENTS.md — SCU Course Planner

**Read this before changing planning / recommendation code.** These rules
encode SCU domain knowledge and product preferences. The codebase already
implements most of them; new code must not regress them.

---

## Run the app

Backend (FastAPI + Gemini agents):
```bash
cd project/api
uvicorn main:app --reload --port 8000 \
  --reload-dir . \
  --reload-dir ../course_planner
```

Frontend (Vite + React, separate terminal):
```bash
cd project/web && npm run dev    # http://localhost:5173
```

Python tests: `cd project && python3 -m pytest tests/`
Vitest tests: `cd project && npm test`

---

## Domain rules (HARD requirements)

### R1 — Lab co-requirement pairing  ✅ implemented

At SCU, courses in these subjects with a trailing-L lab section are taken
in the **same quarter** as the lecture (and vice versa):

```
CSEN  COEN  CSCI  ELEN  ECEN  PHYS  CHEM  BIOL  MECH
```

Examples: `CSEN 20 + CSEN 20L`, `CSEN 194 + CSEN 194L`, `ECEN 153 + ECEN 153L`.

- Never split a lecture/lab pair across quarters.
- The pairer is `_pair_lab_corequirements` in
  `project/course_planner/agents/planning_agent.py`. It uses
  `_resolve_item_codes` so it works even when the Workday row has
  `course=None` and the codes are embedded in the requirement text.
- CSEN ↔ COEN aliases are mirrored in `planned_section_keys` in
  `project/course_planner/utils/scu_course_schedule_xlsx.py`.
- Tests: `tests/test_lab_pairing.py`, `tests/test_lab_pairing_academic_progress_export_format.py`.

### R2 — Prefer double-tagged Core / GE courses  ✅ implemented

When filling an open Core / GE requirement (RTC 3, ELSJ, Advanced Writing,
Arts, etc.), choose a course that **simultaneously** satisfies as many open
requirements as possible. Example: `SCTR 128` covers RTC 3 + ELSJ +
Applied Ethics at once.

- The "CANDIDATE COURSES" prompt block surfaces these as `★` to the LLM
  and sorts double-tagged first. See `_build_schedule_block` in
  `planning_agent.py` and the prompt construction in
  `four_year_planning_agent.py`.
- The category → course reverse index comes from the schedule xlsx
  `Course Tags` column via `load_category_course_index`.
- Tests: `tests/test_category_index.py`,
  `tests/test_open_requirement_resolver.py`.

### R3 — Memory: continuous conversation, not new sessions  ✅ implemented

When the same user keeps chatting in the same session, **update the
existing snapshot in place**. Do NOT spawn a new "Plan · N courses"
row in the left panel for every chat turn.

- `handlePlanGenerated` in `project/web/src/App.tsx` finds
  `activeSessionId`'s snapshot and replaces its `plan_outcome` memory
  entry (delete + write) so storage matches state. A new snapshot is
  created ONLY when `activeSessionId` is null (e.g. after "New Plan").
- Past preferences are restored on login via the `useEffect` that
  rehydrates `missingDetails`, `parsedRows`, and `planSnapshots`.
- Memory kinds:
  - `academic_progress`, `parsed_rows` — singleton, replaced on each
    write (`_SINGLETON_KINDS` in `memory_agent.py`).
  - `plan_outcome` — one per conversation, never text-compacted
    (`_NEVER_COMPACT_KINDS`).
- When a new preference contradicts BACKGROUND CONTEXT (memory),
  CURRENT ASK wins. See the system_instruction in `planning_agent.py`.

### R7 — Follow-up edits are TARGETED diffs  ✅ implemented

A follow-up like "replace ECEN 153 with a Chinese class" or "drop
CSEN 194" must change **only the course(s) the user named** (plus their
lab partners). Every other course in CURRENT STATE stays. Do NOT
regenerate the whole plan — the LLM, asked to re-emit the full list
minus one course, routinely drops unrelated courses, duplicates the
replacement, and reports an inconsistent total.

- Enforced deterministically in `planning_agent.py`:
  - `_named_removal_codes(user_preference)` — extracts the codes the
    user authorized removing (handles "ecen153" with no space and CJK
    text; expands to lab partners + CSEN↔COEN / ECEN↔ELEN aliases).
  - `_reconcile_followup_edit(new_recs, previous_plan, user_preference)`
    — dedups the LLM output and re-adds any CURRENT STATE course it
    dropped that the user did NOT name. Runs on every follow-up turn.
  - `total_units` is always recomputed from the final list.
- Tests: `tests/test_followup_swap.py`.
- Only rebuild the whole plan when the user explicitly asks (e.g. "start
  over", "redo my whole schedule") or clicks **New Plan**.

### R4 — Educational Enrichment: pick the highest-rated course  ⏳ partially

For the "Computer Science and Engineering Major: Educational Enrichment –
Courses" open requirement, the agent should not pick arbitrary courses
from the candidate list — it should prefer the **highest-rated** option
(by instructor rating, see R5).

Current state: the open-requirement resolver returns all candidates that
match the tag; the LLM picks one. New code should:

- When ranking candidates for an open requirement, sort by instructor
  rating descending before sending to the LLM.
- Limit the candidate list shown to the LLM to the top 5 per
  requirement so the model isn't tempted to pick a mediocre option.
- For "Educational Enrichment" specifically, restrict to courses with
  the `core integrations :: <enrichment_tag>` tag set, not the broader
  Pathways pool.

### R5 — Pick the best-rated instructor; show comparison data  ⏳ not yet

When a course has multiple sections next quarter taught by different
instructors, the recommendation must use the section taught by the
**highest-rated** instructor — and the response must include a
side-by-side comparison so the student can see *why*.

Implementation plan (for future agent that picks this up):

1. **Instructor rating source** — add a CSV/JSON at
   `project/course_planner/data/instructor_ratings.csv` with columns
   `instructor_name, rating (0-5), difficulty (0-5), would_take_again_pct,
   source ("rmp" | "scu_eval" | "manual")`. Seed from a one-off RMP
   scrape or manual entry; document the source.
2. **Loader** in `scu_course_schedule_xlsx.py`:
   `load_instructor_ratings() -> dict[str, dict]`. Cache.
3. **Best-section picker** — in the planning agent, when a recommended
   course has multiple sections, choose the section whose
   `meeting_patterns` doesn't conflict with already-scheduled courses
   AND whose instructor has the highest rating. Tie-break by lower
   difficulty.
4. **API response shape** — each `recommended[i]` gets a new optional
   field:
   ```json
   "instructor": {
     "name": "Weijia Shang",
     "rating": 4.2,
     "difficulty": 3.1,
     "alternatives": [
       {"name": "Joe Maglione", "rating": 3.6, "difficulty": 2.8},
       {"name": "Stephen Carter", "rating": 4.8, "difficulty": 4.0}
     ]
   }
   ```
5. **UI** — `CalendarView` and the chat plan summary render a small
   "Instructors" footer per course card with the chosen instructor's
   rating + a tooltip / expandable showing the alternatives table.
6. **Privacy** — instructor ratings are public RMP-style data; do NOT
   ship any non-public SCU course-eval data without policy review.

### R6 — Calendar slot click opens a recommendation popover (no chat noise)  ⏳ not yet

**Current behavior**: clicking an empty calendar slot generates a chat
message like "Can you add something at Mon 10am?" — the suggestion path
goes through the planning agent and the user reads it in chat.

**Required behavior**: clicking a slot opens an **inline popover** on
the calendar at that slot, rendering 3-5 candidate courses ranked by
fit (open requirement, instructor rating, prereq order). The popover
has buttons:

- **Add to plan** — directly updates `planResult.recommended` (no chat
  round-trip) and the next plan request uses the new state.
- **Why this?** — expands a small justification block (open requirement
  it covers, instructor rating, etc.).
- **Show more** — fetches additional candidates for that slot.

Implementation sketch:

1. New API endpoint
   `POST /api/plan/suggest_for_slot` (cheaper than full
   `/api/plan` regeneration) accepting `{day, start_min, end_min,
   missing_details, user_id, exclude_codes[]}`. Returns up to 5
   candidate courses with title, instructor, rating, rationale.
2. Click handler in `project/web/src/components/CalendarView.tsx` —
   when a user clicks an empty cell, open a `<SlotSuggestionPopover />`
   anchored at the cell, call the endpoint, render results.
3. "Add to plan" appends to the local recommended list and the
   `handlePlanGenerated` path still persists the snapshot.
4. **Do NOT** push a synthetic chat message — the popover replaces
   that flow entirely.

---

## Soft preferences

- **Senior Design 3-quarter sequence** (CSEN 194 → 195 → 196 with their
  labs): always scheduled in three consecutive quarters, late in the
  plan (final year). Enforced via prompt rule in
  `four_year_planning_agent.py`.
- **Unit cap**: target 12–16 units/quarter, never exceed 20. The agent
  enforces this; LLM must self-consistently set `total_units` =
  Σ `units`.
- **Course titles**: always pulled from the schedule xlsx via
  `course_title_for` — never trust the LLM's `title` field. (Was the
  source of the "CSEN 122L = Data Structures" bug.)
- **Time conflicts**: never schedule two courses with overlapping
  meeting windows on a shared weekday. `_partition_recommended` flags
  conflicts and runs the LLM correction loop.

---

## When you're tempted to relax a rule

If a rule above forces the LLM to drop courses or graduates ugly errors,
**fix the data layer** (schedule xlsx, category index, instructor
ratings) before relaxing the rule. The rules exist because every one of
them has fired as a real production bug.
