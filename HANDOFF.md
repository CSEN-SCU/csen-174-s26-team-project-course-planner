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
cd project/course_planner && python3 -m pytest tests/
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

A second planning engine alongside `run_planning_agent`. **The full A→E
track is DONE and wired to HTTP** at `POST /api/plan/v2`. Legacy
`/api/plan` stays the default; set `MULTI_AGENT_PLAN=1` to make it
delegate to the multi-agent engine.

```
START → planner → verifier ─[issues & passes<3]→ planner (loop)
                          ├─[clean]→ Send(instructor_one) × N  (parallel)
                          └─[no courses]──────────────────────→ assembler → END
```

| Node | LLM? | Role |
|------|------|------|
| Planner | yes — **ReAct tool-calling** | calls `search_schedule` / `get_open_req_candidates` / `get_lab_partner` before proposing courses; native Gemini function-calling (no langchain). `PLANNER_REACT=0` → single-shot fallback |
| Verifier | no (pure code) | hallucination, time-conflict, missing-lab, uncovered-Core checks; routes back to planner / fans out / skips |
| InstructorSelector | no | ranks sections by **real instructor rating** (catalog `instructor_ratings.csv`), tie-break difficulty; parallel via `Send` |
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

### 2.1 What's DONE (was STEP A–E)

- **A — instructor ratings** ✅ `data/instructor_ratings.csv` (seed,
  `source=seed_placeholder`) + `load_instructor_ratings` / `course_units_for`
  loaders; picker ranks by rating. *Real RMP data still TODO* — the seed
  rows are placeholders; `requirements.txt` already has `ratemyprofessors-client`.
- **B — tool-calling planner** ✅ native Gemini function-calling ReAct loop.
- **C — parallel fan-out** ✅ `Send` API, one `instructor_one` per course.
- **D — checkpointing + HITL** ✅ Memory/SQLite savers + `interrupt_before`.
- **E — HTTP wiring** ✅ `/api/plan/v2` + review/resume.

### 2.2 Eval harness — `agents`-quality measurement (BUILT)

`project/course_planner/evals/`: 7 deterministic scorers (no LLM-judge) —
`no_hallucination`, `no_time_conflicts`, `labs_paired`, `unit_cap`,
`titles_correct`, `open_req_coverage`, `no_injection_leak`. Run an A/B:
```bash
cd project/course_planner && python -m evals.run_eval --engine both
```
Tests: `test_eval_scorers.py` (25, offline).

### 2.3 Still open

- **R6 — calendar slot-click suggestion popover**: not started (spec in
  AGENTS.md §R6). Current slot-click only prefills a chat message.
- **Real instructor ratings**: replace the seed CSV placeholders.
- **Frontend on `/api/plan/v2`**: the web app still calls legacy `/api/plan`;
  the multi-agent engine is backend-only / opt-in.

---

## 3. AGENTS.md domain rules — status

| Rule | Status | Notes |
|------|--------|-------|
| R1 lab co-requirement pairing | ✅ done | `_pair_lab_corequirements` |
| R2 prefer double-tagged Core/GE | ✅ done | `★` in schedule block + category index |
| R3 same conversation = same snapshot | ✅ done | `handlePlanGenerated` in-place update |
| R4 Educational Enrichment: highest-rated, enrichment tag only | ⏳ partial | ratings loader exists; enrichment-tag scoping still loose |
| R5 best-rated instructor + comparison table | ✅ done (seed data) | multi-agent picker ranks by rating; **real RMP data TODO** |
| R6 calendar slot click → suggestion popover | ⏳ not started | needs `POST /api/plan/suggest_for_slot` + `<SlotSuggestionPopover/>` |
| R7 follow-up edits are targeted diffs | ✅ done | `_reconcile_followup_edit` + `_named_removal_codes`; `test_followup_swap.py` |

### 3.1 Recent fixes not to regress
- **Units from catalog**: `course_units_for` overrides LLM-invented units
  (CSEN 122=4, 122L=1) in both planning agents; `test_course_units_override.py`.
- **Manual "+ Add course"**: `GET /api/courses` (746 courses) +
  `AddCoursePicker.tsx` add courses (and lab partner) directly, no AI.
- **New Plan** always gives feedback (message + view switch + focus).
- **Lab grouping** in chat summary (lab nested under its lecture).

---

## 4. Red-team findings — status

From `Copy of Red Team — SCU Course Planner.pdf`. Several were merged by
teammates via PRs (#26 #27 #28) and direct commits.

| # | Finding | Status |
|---|---------|--------|
| 1 | Rate limiting on planning endpoints | ✅ merged (`4322cbb`) — `middleware/rate_limit.py`; verified live (429s) |
| 2 | Session/memory restoration after login | ✅ effectively done (parsedRows + memory hydration, singleton kinds) |
| 3 | Workday sync auth + URL allowlist + error scrubbing | Removed for v1; manual upload is the only Academic Progress ingestion path |
| 4 | New Plan reset clears all state | ⚠️ verify — `handleNewPlan` clears most; add a Vitest test to pin it |
| 5 | 4-year plan blind to electives/goals | ⏳ schema split done in agent (electives/goals params); UI inputs + endpoint wiring may be incomplete — verify `four_year_plan.py` + `FourYearPlanView.tsx` |
| 6 | 4-year plan intermittently empty | ✅ merged (`0850dc9`) — structured errors |
| 7 | Prompt injection via user_preference | ✅ merged (`1b1e6b1` + teammate `b083746`) — `_sanitize_user_text`, output denylist |
| 8 | System-prompt exfiltration | ⚠️ partial — `_SYSTEM_PROMPT_LEAK_PHRASES` + `_contains_system_prompt_leak` exist in `planning_agent.py`; confirm it's applied to `advice`/`assistant_reply` and add the `GET /api/diagnostics/leak_attempts` admin endpoint (not yet present) |
| RAI | Responsible-AI: data disclosure, PII scrub, lifecycle | ✅ partial — Data Disclosure page merged (PRs #26/#27); PII scrub util + "Delete my data" endpoint still TODO |

> The 9 background red-team subagents I launched earlier mostly hit the API
> rate limit and produced little; the merged fixes above came from teammate
> PRs + direct commits, not those agents. Their worktrees are gone.

---

## 5. Known tech debt / gotchas

- **Manual Academic Progress upload only**: students export "View My Academic
  Progress" from Workday as `.xlsx` / `.xlsm` and upload it with the paperclip.
  The Playwright Workday sync path and `SCU_WORKDAY_URL` env var were removed.
- **Pre-existing broken tests** (NOT regressions — both reference symbols
  removed in earlier sprints):
  - `tests/test_schedule_filter.py` — imports `_filter_to_schedule` (deleted).
  - `tests/test_orchestrator_injection.py` — 3 of 8 fail
    (`MEMORY_INJECT_CHAR_BUDGET` / orchestrator expectations drifted).
  - Decide: update or delete these.
- **Stale `.pyc`**: `auth/__pycache__/streamlit_auth.*.pyc` remain after the
  Streamlit source was removed. Harmless; `find . -name '*.pyc' -delete` to clean.
- **Memory is flat files**, not a DB. Singleton kinds (`academic_progress`,
  `parsed_rows`) replace-on-write; `plan_outcome` accumulates and is never
  text-compacted (`_NEVER_COMPACT_KINDS` in `memory_agent.py`).
- **Two Python envs exist** — anaconda (has all deps incl. langgraph) vs
  `project/api/.venv` (missing some). uvicorn must run under the anaconda one.

---

## 6. Key file map

```
project/
  api/
    main.py                          FastAPI app + router mounts
    middleware/rate_limit.py         in-memory token-bucket limiter (RT#1)
    routers/
      plan.py                        /api/plan (legacy) + /api/plan/v2 (multi-agent) + review/resume
      courses.py                     GET /api/courses (catalog for manual "+ Add course")
      four_year_plan.py              POST /api/four-year-plan
      upload.py                      POST /api/upload/transcript
      memory.py                      GET/DELETE /api/memory/{uid}
      auth.py                        login/register + Google OAuth
                                     (NOTE: workday.py was REMOVED)
  course_planner/
    agents/
      planning_agent.py              run_planning_agent (LEGACY, canonical)
      four_year_planning_agent.py    run_four_year_plan_agent
      memory_agent.py                flat-file memory store
      multi_agent/                   LangGraph engine (§2) — tools/graph/planner_react
    evals/                           plan-quality scorers + A/B runner (§2.2)
    utils/
      scu_course_schedule_xlsx.py    schedule/category/title/units/ratings/list_offered_courses
      academic_progress_xlsx.py      Academic Progress xlsx parser
    data/instructor_ratings.csv      instructor ratings (seed placeholders — replace)
    SCU_Find_Course_Sections.xlsx    next-term schedule (source of truth)
    View_My_Academic_Progress.xlsx   sample transcript
    tests/                           pytest + vitest live here together
  web/src/
    App.tsx                          root state + handlers; takes {userId, onSignOut} props
                                     (auth lifted OUT of App by teammate refactor)
    components/
      ChatPanel.tsx                  chat + manual Academic Progress upload
      AddCoursePicker.tsx            "+ Add course" searchable dropdown (manual add)
      CalendarView.tsx               "This Quarter" weekly grid (R6 target)
      FourYearPlanView.tsx           4-year grid (completed gray + recommended)
      LeftPanel.tsx                  sessions list + New Plan (login moved out)
    api/client.ts                    fetch wrappers (incl. listCourses)
    types/index.ts                   shared TS types
AGENTS.md                            domain rules (READ FIRST)
HANDOFF.md                           this file
```

---

## 7. Definition of done for the LangGraph track

1. STEP A merged: real ratings, picker ranks by rating, legacy path also
   emits `instructor` + `alternatives`. Tests green.
2. STEP B merged: planner does tool-calling; tests stub tool calls.
3. STEP C merged: parallel `Send` fan-out; tests assert N dispatches.
4. STEP D merged: checkpointer; interrupt/resume test green.
5. STEP E merged: `/api/plan/v2` behind flag; legacy unchanged.
6. Full suite green except the two known-broken legacy files (fix or delete).
7. `cd project/web && npx tsc --noEmit` clean.
