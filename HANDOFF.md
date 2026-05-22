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

## 2. LangGraph multi-agent system (NEW — `agents/multi_agent/`)

A parallel implementation to `run_planning_agent`. **Not wired to any HTTP
endpoint yet.** Opt-in via `from agents.multi_agent import run_multi_agent_plan`.

```
START → planner → verifier ─[issues & passes<3]→ planner (loop)
                            └─[clean]→ fan_out_instructor → assembler → END
```

| Node | LLM? | Role |
|------|------|------|
| Planner | yes (Gemini) | propose recommended courses; re-run with verifier feedback embedded |
| Verifier | no (pure code) | hallucination, time-conflict, missing-lab, uncovered-Core checks |
| InstructorSelector | no (stub) | pick best-rated section + alternatives table |
| Assembler | no | merge plan + instructor picks into final response |

Files:
- `agents/multi_agent/tools.py` — 9 deterministic tools wrapping existing
  utils (`ALL_TOOLS` registry).
- `agents/multi_agent/graph.py` — `PlanningState` TypedDict, the 4 nodes,
  `build_graph()`, `run_multi_agent_plan()`.
- `tests/test_multi_agent_graph.py` — 6 tests, Gemini stubbed, all green.

### 2.1 BACKLOG — LangGraph next steps (in priority order)

**STEP A — R5 instructor ratings (IN PROGRESS, not committed)**
- Create `project/course_planner/data/instructor_ratings.csv` with columns:
  `instructor_name,rating,difficulty,would_take_again_pct,source`
- The schedule xlsx has **579 distinct instructors** (extract via
  `load_schedule_section_index()` → entry["instructors"]). Seed a subset with
  `source="seed"`; real data needs an RMP scrape or manual entry — DO NOT
  fabricate and present as real; mark provenance in the `source` column.
- Add `load_instructor_ratings() -> dict[str, dict]` (cached) in
  `utils/scu_course_schedule_xlsx.py`.
- Replace the stub in `agents/multi_agent/tools.py::tool_get_instructor_rating`.
- Make `agents/multi_agent/graph.py::_select_best_section` actually rank by
  rating desc, tie-break by lower difficulty, and skip sections that
  time-conflict with already-chosen courses.
- Tests: ratings loader; best-section picker prefers higher rating; missing
  rating falls back to first section without crashing.
- Mirror into the LEGACY path too (`agents/planning_agent.py`) per AGENTS.md
  R5: add an `instructor` field to each `recommended[i]` with `alternatives[]`.

**STEP B — Tool-calling Planner (ReAct)**
- Today the planner is a single prompt. Upgrade it to decide *when* to call
  `search_schedule` / `get_open_req_candidates` / `get_lab_partner`.
- Two options:
  1. `langchain-google-genai` `ChatGoogleGenerativeAI.bind_tools()` +
     LangGraph prebuilt `ToolNode` / `create_react_agent`. Cleanest but adds
     the `langchain-google-genai` dependency.
  2. Native Gemini function-calling via `google.genai` `Tool`/`FunctionDeclaration`,
     hand-rolled tool loop. No new dep, more code.
- Recommend option 1 for the multi_agent module (it's already LangGraph).
- Keep the deterministic Verifier as-is (no LLM there).
- Tests: stub the chat model to emit a tool call then a final answer; assert
  the tool was invoked and the loop terminated.

**STEP C — Parallel InstructorSelector via `Send` API**
- Current `_all_instructors_node` loops sequentially. Replace with LangGraph
  `Send` fan-out: one InstructorSelector invocation per recommended course,
  run concurrently, results merged via the existing `_merge_dicts` reducer on
  `instructor_assignments`.
- Pattern: a conditional edge from verifier returns
  `[Send("instructor_one", {"course": code}) for code in plan]`.
- Tests: 3 courses → 3 Send dispatches → all 3 assignments present.

**STEP D — Checkpointing / resumability**
- Add a checkpointer (`langgraph.checkpoint.memory.MemorySaver` for dev;
  `langgraph.checkpoint.sqlite.SqliteSaver` backed by `data/app.db` for prod).
- Compile graph with `checkpointer=...`; invoke with
  `config={"configurable": {"thread_id": <session_id>}}`.
- Enables: resume an interrupted plan; human-in-the-loop interrupt before
  committing a plan that drops a course.
- Tests: interrupt after planner, resume, assert state continuity.

**STEP E — Wire to HTTP (after A–D stable)**
- New route `POST /api/plan/v2` in `project/api/routers/plan.py` calling
  `run_multi_agent_plan`. Gate behind env flag `MULTI_AGENT_PLAN=1` or a
  per-request `?engine=v2`. Keep `/api/plan` (legacy) as default.

---

## 3. AGENTS.md domain rules — status

| Rule | Status | Notes |
|------|--------|-------|
| R1 lab co-requirement pairing | ✅ done | `_pair_lab_corequirements` |
| R2 prefer double-tagged Core/GE | ✅ done | `★` in schedule block + category index |
| R3 same conversation = same snapshot | ✅ done | `handlePlanGenerated` in-place update |
| R4 Educational Enrichment: highest-rated, enrichment tag only | ⏳ partial | depends on R5 ratings; restrict to `core integrations::` tag |
| R5 best-rated instructor + comparison table | ⏳ in progress | STEP A above |
| R6 calendar slot click → suggestion popover (no chat noise) | ⏳ not started | spec in AGENTS.md §R6; needs `POST /api/plan/suggest_for_slot` + `<SlotSuggestionPopover/>` |

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
      plan.py                        POST /api/plan (legacy single-shot)
      four_year_plan.py              POST /api/four-year-plan
      upload.py                      POST /api/upload/transcript
      memory.py                      GET/DELETE /api/memory/{uid}
      auth.py                        login/register + Google OAuth
  course_planner/
    agents/
      planning_agent.py              run_planning_agent (LEGACY, canonical)
      four_year_planning_agent.py    run_four_year_plan_agent
      memory_agent.py                flat-file memory store
      multi_agent/                   NEW LangGraph system (§2)
        tools.py  graph.py  __init__.py
    utils/
      scu_course_schedule_xlsx.py    schedule/category/title/conflict helpers
      academic_progress_xlsx.py      Workday xlsx parser
    SCU_Find_Course_Sections.xlsx    next-term schedule (source of truth)
    View_My_Academic_Progress.xlsx   sample transcript
    tests/                           pytest + vitest live here together
  web/src/
    App.tsx                          root state, login hydration, handlers
    components/
      ChatPanel.tsx                  chat + manual Academic Progress upload
      CalendarView.tsx               "This Quarter" weekly grid (R6 target)
      FourYearPlanView.tsx           4-year grid (completed gray + recommended)
      LeftPanel.tsx                  login/register, sessions, New Plan
    api/client.ts                    fetch wrappers
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
