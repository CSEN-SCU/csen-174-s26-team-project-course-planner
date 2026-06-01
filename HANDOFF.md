# HANDOFF — SCU Course Planner

Self-contained spec for an LLM taking over development. Read `AGENTS.md`
(repo root) first for the domain rules; this file is the work backlog +
current state.

---

## 0. Project at a glance

- **Location**: `/Users/huangjiasheng/Desktop/course-planner/`
- **Backend**: FastAPI at `project/api/` (uvicorn, port 8000)
- **Frontend**: React + Vite at `project/web/` (port 5173)
- **Agents + utils + tests**: `project/course_planner/`
- **LLM**: Google Gemini via `google.genai` SDK (`agents/gemini_client.py`)
- **Memory**: flat per-user markdown files in
  `project/course_planner/data/memory/<uid>.md` (NOT a DB)
- **Auth DB**: SQLite at `project/course_planner/data/app.db`
  (`auth/users_db.py`)

### Run

```bash
# Backend
cd project/api
uvicorn main:app --reload --port 8000 \
  --reload-dir . --reload-dir ../course_planner

# Frontend
cd project/web && npm run dev          # http://localhost:5173
```

### Test

```bash
# Python
cd project && python3 -m pytest tests/
# Vitest (frontend)
cd project && npm test
```

> Use the interpreter that has deps installed: on this machine that is
> `/opt/anaconda3/bin/python3.13`, NOT the api/.venv.

### Env (`project/course_planner/.env`, gitignored)

```
GEMINI_API_KEY=...
GOOGLE_CLIENT_ID=...                 # Google OAuth (web client)
GOOGLE_CLIENT_SECRET=...
GOOGLE_OAUTH_REDIRECT_URI=http://localhost:8000/api/auth/google/callback
FRONTEND_BASE_URL=http://localhost:5173
SCU_PLANNER_COOKIE_KEY=<random 48 bytes>
```

---

## 1. Data flow (how a plan is made)

```
Manual Workday Academic Progress xlsx upload
   │
   ▼
upload.py ─► parse_academic_progress_xlsx()
   │
   ▼
missing_details  (NOTE: course_code is almost always None — codes live in the
`requirement` TEXT, e.g. "CSEN/COEN 122 & 122L")
   │
   ▼
run_planning_agent(missing_details, user_preference, memory, previous_plan)
   │
   ├─ load schedule index + category(tag) index + course-titles index from
   │  project/course_planner/SCU_Find_Course_Sections.xlsx
   ├─ build CONFIRMED-IN-SCHEDULE prompt block (+ open Core/GE candidates,
   │  double-tagged marked ★)
   ├─ Gemini call (response_schema = PLANNING_SCHEMA)
   ├─ validate → partition (hallucination + time-conflict) → feedback retry (≤2)
   ├─ _pair_lab_corequirements (add missing labs)
   ├─ override titles from schedule xlsx (never trust LLM title)
   └─ return recommended[], total_units, advice, assistant_reply, warnings
```

Key invariant: **the LLM's course codes are never trusted**; everything is
re-validated against the live schedule index.

---

## 2. LangGraph multi-agent system — `agents/multi_agent/` (BUILT)

An experimental planning engine is wired to HTTP at `POST /api/plan/v2`.
Production `/api/plan` uses the LLM course-selection planner.

```
START → planner → verifier ─[issues & passes<3]→ planner (loop)
                          ├─[clean]→ Send(instructor_one) × N  (parallel)
                          └─[no courses]──────────────────────→ assembler → END
```

| Node | LLM? | Role |
|------|------|------|
| Planner | yes — **ReAct tool-calling** | calls `search_schedule` / `get_open_req_candidates` / `get_lab_partner` before proposing courses; native Gemini function-calling (no langchain). `PLANNER_REACT=0` → single-shot fallback |
| Verifier | no (pure code) | hallucination, time-conflict, missing-lab, uncovered-Core checks; routes back to planner / fans out / skips |
| InstructorSelector | no | ranks sections by **real instructor rating** (catalog `instructor_ratings.csv`, 436/583 courses), tie-break difficulty; parallel via `Send` |
| Assembler | no | merge plan + instructor picks into final response |

Files:
- `agents/multi_agent/tools.py` — 9 deterministic tools (`ALL_TOOLS`).
- `agents/multi_agent/planner_react.py` — bounded ReAct loop (`run_planner_react`).
- `agents/multi_agent/graph.py` — `PlanningState`, nodes, `Send` fan-out,
  checkpointer factories (`make_memory_checkpointer` / `make_sqlite_checkpointer`),
  HITL helpers (`start_plan_with_review` / `resume_plan` / `get_plan_state`),
  `run_multi_agent_plan(... thread_id, checkpointer)`.
- HTTP: `POST /api/plan/v2`, `/api/plan/v2/review`, `/api/plan/v2/resume`
  (`project/api/routers/plan.py`).
- Tests: `test_multi_agent_graph.py`, `test_planner_react.py`,
  `test_instructor_fanout.py`, `test_instructor_ratings.py`,
  `test_checkpoint_resume.py`, `test_plan_v2_endpoint.py` — all green.

### 2.1 What's DONE (STEP A–E + R4–R6)

- **A — instructor ratings** ✅ `data/instructor_ratings.csv` — **real RMP
  data, 436/583 courses found** (`source=rmp`); scraper at
  `scripts/scrape_rmp_ratings.py`. Picker ranks by rating.
- **B — tool-calling planner** ✅ native Gemini function-calling ReAct loop.
- **C — parallel fan-out** ✅ `Send` API, one `instructor_one` per course.
- **D — checkpointing + HITL** ✅ Memory/SQLite savers + `interrupt_before`.
- **E — HTTP wiring** ✅ `/api/plan/v2` + review/resume.
- **R4 — Educational Enrichment** ✅ `enrichment` tag scoping enforced;
  rating sort + top-5 cap in `planning_agent.py`.
- **R5 — best-rated instructor** ✅ real RMP data replaces seed placeholders.
- **R6 — slot-click popover** ✅ see §3 below.

### 2.2 Eval harness — `agents`-quality measurement (BUILT)

`project/course_planner/evals/`: 7 deterministic scorers (no LLM-judge) —
`no_hallucination`, `no_time_conflicts`, `labs_paired`, `unit_cap`,
`titles_correct`, `open_req_coverage`, `no_injection_leak`. Run the active
planner eval:
```bash
cd project/course_planner && python -m evals.run_eval --engine llm
```
Tests: `test_eval_scorers.py` (25, offline).

### 2.3 Still open

- **Frontend on `/api/plan/v2`**: the web app still calls `/api/plan`; the
  multi-agent engine is available only through explicit `/api/plan/v2` routing.

---

## 3. AGENTS.md domain rules — status

| Rule | Status | Notes |
|------|--------|-------|
| R1 lab co-requirement pairing | ✅ done | `_pair_lab_corequirements` |
| R2 prefer double-tagged Core/GE | ✅ done | `★` in schedule block + category index |
| R3 same conversation = same snapshot | ✅ done | `handlePlanGenerated` in-place update |
| R4 Educational Enrichment: highest-rated, enrichment tag only | ✅ done | enrichment-tag filter + rating sort + top-5 cap in `planning_agent.py` |
| R5 best-rated instructor + comparison table | ✅ done | real RMP data (436/583); multi-agent picker ranks by rating |
| R6 calendar slot click → suggestion popover | ✅ done | `POST /api/plan/suggest_for_slot` + `<SlotSuggestionPopover/>` wired; `clampPosition` viewport fix; 90-min time window; outside-click close; `test_r6_slot_suggestion.py` |
| R7 follow-up edits are targeted diffs | ✅ done | `_reconcile_followup_edit` + `_named_removal_codes`; `test_followup_swap.py` |

### 3.1 Recent fixes not to regress

- **Units from catalog**: `course_units_for` overrides LLM-invented units
  (CSEN 122=4, 122L=1) in both planning agents; `test_course_units_override.py`.
- **Manual "+ Add course"**: `GET /api/courses` (~700 courses) +
  `AddCoursePicker.tsx` — shows search hint on empty query (prevents
  confusing "only ARTS courses" first-render); adds lab partner automatically.
- **New Plan** always gives feedback (message + view switch + focus);
  also resets `fourYearGenerating` + `slotPopoverOpen/Data` (RT#4, 9 Vitest pins).
- **Lab grouping** in chat summary (lab nested under its lecture).
- **4-year plan preferences**: `FourYearPlanView` has electives/goals textarea;
  `handleGenerateFourYearPlan(preferences)` passes it to the API (RT#5).
- **Slot popover rate limit**: `suggest_for_slot` uses `"slot_suggest"` bucket
  (60/min IP, 120/min user) — independent of the heavy plan-generation quota.
- **errFromBody**: rate-limited 429 responses now show a friendly
  "Too many requests — please wait N seconds" instead of raw JSON.
- **RT#8 diagnostics**: `GET /api/diagnostics/leak_attempts` admin endpoint
  exists (`routers/diagnostics.py`); `score_no_injection_leak` scorer confirmed
  to scan both `advice` and `assistant_reply` fields.

---

## 4. Red-team findings — status

From `Copy of Red Team — SCU Course Planner.pdf`.

| # | Finding | Status |
|---|---------|--------|
| 1 | Rate limiting on planning endpoints | ✅ done — `middleware/rate_limit.py`; `"plan"` + `"four_year_plan"` + `"slot_suggest"` buckets; verified live (429s) |
| 2 | Session/memory restoration after login | ✅ done — parsedRows + memory hydration, singleton kinds |
| 3 | Workday sync auth + URL allowlist + error scrubbing | Removed for v1; manual upload is the only Academic Progress ingestion path |
| 4 | New Plan reset clears all state | ✅ done — `handleNewPlan` resets fourYearGenerating + slotPopoverOpen/Data; 9 Vitest pins in `new-plan-reset.test.tsx` cover the full state contract |
| 5 | 4-year plan blind to electives/goals | ✅ done — `FourYearPlanView` has preferences textarea; wired through `handleGenerateFourYearPlan(preferences)` → API `preferences` field → agent `user_preference` |
| 6 | 4-year plan intermittently empty | ✅ done — structured errors |
| 7 | Prompt injection via user_preference | ✅ done — `_sanitize_user_text`, output denylist |
| 8 | System-prompt exfiltration | ✅ done — `_contains_system_prompt_leak` applied to `advice`/`assistant_reply`; `GET /api/diagnostics/leak_attempts` endpoint; `no_injection_leak` scorer in eval harness |
| RAI | Responsible-AI: data disclosure, PII scrub, lifecycle | ✅ done — Data Disclosure page (expanded copy, PRs #26/#27); `sanitize_parsed_rows` strips grades; `DELETE /api/auth/user/{id}/data` wipes memory + SQLite + storage; `purge_user_storage` + `_redact_pii`; frontend confirm dialog; 9 tests pass |

---

## 5. Known tech debt / gotchas

- **Manual Academic Progress upload only**: students export "View My Academic
  Progress" from Workday as `.xlsx` / `.xlsm` and upload it with the paperclip.
  There is no in-app or CLI browser automation path.
- **Tests consolidated into `project/tests/`**: all pytest files now live in
  `project/tests/` (single CI home). The old `project/course_planner/tests/`
  directory still exists but only has non-test support files.
- **Stale `.pyc`**: `auth/__pycache__/streamlit_auth.*.pyc` remain after the
  Streamlit source was removed. Harmless; `find . -name '*.pyc' -delete` to clean.
- **Memory is flat files**, not a DB. Singleton kinds (`academic_progress`,
  `parsed_rows`) replace-on-write; `plan_outcome` accumulates and is never
  text-compacted (`_NEVER_COMPACT_KINDS` in `memory_agent.py`).
- **Two Python envs exist** — anaconda (has all deps incl. langgraph) vs
  `project/api/.venv` (missing some). uvicorn must run under the anaconda one.
- **System-prompt exfiltration detection is substring-only**: `_SYS_LEAK_PHRASES`
  checks for verbatim phrases. A paraphrase or translation would bypass it.
  Acceptable for now; upgrade to LLM-judge if this becomes a concern.
- **RMP data is 436/583 courses** (74%): remaining 147 courses have no rating
  data and fall back to a neutral default. Re-run `scripts/scrape_rmp_ratings.py`
  when new schedule data arrives.

---

## 6. Key file map

```
project/
  api/
    main.py                          FastAPI app + router mounts
    middleware/rate_limit.py         token-bucket limiter: "plan" / "four_year_plan" / "slot_suggest"
    routers/
      plan.py                        /api/plan (legacy) + /api/plan/v2 + suggest_for_slot (R6)
      courses.py                     GET /api/courses (catalog for manual "+ Add course")
      four_year_plan.py              POST /api/four-year-plan (accepts `preferences` field, RT#5)
      upload.py                      POST /api/upload/transcript
      memory.py                      GET/DELETE /api/memory/{uid}
      diagnostics.py                 GET /api/diagnostics/leak_attempts (RT#8 admin)
      auth.py                        login/register + Google OAuth
  course_planner/
    agents/
      planning_agent.py              run_planning_agent (LEGACY, canonical) + suggest_courses_for_slot
      four_year_planning_agent.py    run_four_year_plan_agent (accepts user_preference/preferences)
      memory_agent.py                flat-file memory store
      multi_agent/                   LangGraph engine (§2) — tools/graph/planner_react
    evals/                           plan-quality scorers + A/B runner (§2.2)
    utils/
      scu_course_schedule_xlsx.py    schedule/category/title/units/ratings/list_offered_courses
      academic_progress_xlsx.py      Academic Progress xlsx parser
    data/instructor_ratings.csv      real RMP data (436/583 courses, source=rmp)
    scripts/scrape_rmp_ratings.py    RMP scraper (re-run when schedule updates)
    SCU_Find_Course_Sections.xlsx    next-term schedule (source of truth)
    View_My_Academic_Progress.xlsx   sample transcript
  tests/                             ALL pytest + vitest tests (single home post-consolidation)
    app/new-plan-reset.test.tsx      RT#4: 9 Vitest pins for handleNewPlan state contract
    test_r6_slot_suggestion.py       R6: slot suggestion endpoint tests
    test_diagnostics_leak_attempts.py RT#8: diagnostics endpoint tests
    conftest.py                      autouse rate-limiter reset fixture
  web/src/
    App.tsx                          root state + handlers; takes {userId, onSignOut} props
    components/
      ChatPanel.tsx                  chat + manual Academic Progress upload
      AddCoursePicker.tsx            "+ Add course" searchable dropdown (search-gated, no empty list)
      CalendarView.tsx               "This Quarter" weekly grid; onSlotClick passes clientX/Y
      SlotSuggestionPopover.tsx      R6 popover — clampPosition, outside-click close, Show more
      FourYearPlanView.tsx           4-year grid + electives/goals textarea (RT#5)
      LeftPanel.tsx                  sessions list + New Plan
    api/client.ts                    fetch wrappers; errFromBody handles rate_limited object detail
    types/index.ts                   shared TS types
AGENTS.md                            domain rules (READ FIRST)
HANDOFF.md                           this file
```

---

## 7. Definition of done — all tracks complete ✅

1. ~~STEP A: real ratings~~ ✅ 436/583 RMP courses
2. ~~STEP B: tool-calling planner~~ ✅
3. ~~STEP C: parallel fan-out~~ ✅
4. ~~STEP D: checkpointer + HITL~~ ✅
5. ~~STEP E: `/api/plan/v2` behind flag~~ ✅
6. ~~Full suite green~~ ✅ (broken `test_schedule_filter` + `test_orchestrator_injection` hardened)
7. ~~`tsc --noEmit` clean~~ ✅

**Stretch items — all complete ✅**

| # | Item | How |
|---|------|-----|
| S1 | Wire frontend to `/api/plan/v2` | `VITE_USE_PLAN_V2=1` env var in `web/src/api/client.ts` routes `generatePlan` to the multi-agent endpoint; test in `tests/app/plan-v2-routing.test.ts` |
| S2 | `plan_outcome` memory compaction | Removed `plan_outcome` from `_NEVER_COMPACT_KINDS` in `memory_agent.py`; old plan summaries are now LLM-compacted like `preference`/`note` entries; tests in `test_memory_compaction.py` + guard in `test_memory_singleton_and_protection.py` |
| S3 | LLM-judge leak detection | Added `_llm_judge_system_prompt_leak()` in `planning_agent.py`; activated by `SYS_LEAK_LLM_JUDGE=1`; catches paraphrases/translations that substring denylist misses; falls back gracefully if API unavailable; 8 tests in `test_llm_judge_leak_detection.py` |
