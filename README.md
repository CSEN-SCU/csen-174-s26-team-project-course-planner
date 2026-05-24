[![Review Assignment Due Date](https://classroom.github.com/assets/deadline-readme-button-22041afd0340ce965d47ae6ef1cefeee28c7c493a6346c4f15d667ab976d596c.svg)](https://classroom.github.com/a/NfqHRKdw)

# SCU Course Planner (CSEN 174)

## Team

**SCU Course Planner** · Jason · Ismael · Joey · Jiasheng

---

## SCU Course Planner

A web app for Santa Clara University students. Manually export SCU **View My
Academic Progress** from Workday as an Excel file, upload it, describe
preferences in natural language, and get a **recommended next-quarter schedule**
and **multi-quarter graduation plan** with **RateMyProfessor** enrichment and a
**weekly calendar** preview (when **Find Course Sections** `.xlsx` is present).
Per-user **long-term memory** (RAG) and **follow-up chat replies** support
iterative planning across sessions.

Two services compose the app:

| Path | Stack | Role |
|------|-------|------|
| [`project/api/`](project/api/) | FastAPI + Python agents | REST API for auth, Academic Progress upload, plan generation, four-year plan, memory CRUD |
| [`project/web/`](project/web/) | React + Vite + Tailwind | SPA: Google sign-in + chat + calendar + 4-year grid |
| [`project/course_planner/`](project/course_planner/) | Python package | Shared **agents**, **SQLite + sqlite-vec**, **auth/users_db**, and **xlsx parsers** used by the FastAPI service |

### Current implementation

| Area | Module | What it does |
|------|--------|----------------|
| Auth | `project/api/routers/auth.py`, `project/course_planner/auth/users_db.py`, `auth/google_oauth.py` | **Google OAuth** sign-in; SQLite stores OAuth-linked user ids |
| Database | `project/course_planner/db/connection.py`, `db/migrate.py`, `db/schema.sql` | SQLite at `project/course_planner/data/app.db` (gitignored): `users`, `memory_items`, **sqlite-vec** `memory_vec` for embeddings |
| Memory (RAG) | `project/course_planner/agents/memory_agent.py` | **Gemini `text-embedding-004`** (fallback hash vectors if no API key); `write` / `retrieve` / list / delete — **scoped by `user_id`** |
| Orchestration | `project/api/routers/plan.py`, `agents/memory_agent.py` | Plan routes load memory, call **planning_agent**, write outcomes back; `orchestrator.py` wraps the same flow for tests |
| Planning | `project/course_planner/agents/planning_agent.py` | **Gemini** structured JSON: `recommended`, `total_units`, `advice`, **`assistant_reply`**. **Lecture+lab pairs** (e.g. CSEN 194 + CSEN 194L) when both appear in the gap; retries / fallback models; **`meta` / `warnings` / per-course `alternatives`**. Prompt-injection sanitiser on user text |
| Four-year plan | `project/course_planner/agents/four_year_planning_agent.py` | Multi-quarter graduation grid; surfaces open Core/GE candidates via Course-Tags index; typed `EmptyPlanError` / `InconsistentPlanError` |
| Requirement parsing | `project/course_planner/utils/academic_progress_xlsx.py` | Parses DegreeWorks export; builds `missing_details` and `parsed_rows` |
| Professor ratings | `project/course_planner/agents/professor_agent.py` | RateMyProfessor GraphQL (parallel); aligns to Find Course instructors when possible |
| Rate limiting | `project/api/middleware/rate_limit.py` | Per-IP, per-user, per-user-concurrency token bucket on `/api/plan`, `/api/four-year-plan` |
| Calendar + 4-year UI | `project/web/src/components/CalendarView.tsx`, `FourYearPlanView.tsx` | Mon–Fri weekly grid plus 4-year graduation grid overlaying completed transcript history with AI recommendations |
| **Multi-agent planner (LangGraph)** | `project/course_planner/agents/multi_agent/` | **Experimental** Planner ↔ Verifier ↔ InstructorSelector graph with tool-calling, parallel fan-out, checkpointing + human-in-the-loop. Exposed at `POST /api/plan/v2`. See [section below](#multi-agent-planner-langgraph) |
| **Eval harness** | `project/course_planner/evals/` | Deterministic rule-based scorers (R1–R6 + injection safety) + A/B runner to compare engines |

### Tests

From `project/`:

```bash
cd project
python3 -m pytest tests/
```

### Architecture (high level)

```
Manual Academic Progress export (.xlsx/.xlsm)
        ↓
Requirement Parser → missing_details + parsed_rows
        ↓
[FastAPI /api/plan or /api/four-year-plan]
        ↓
Memory retrieve + planning_agent (Gemini)  ←  preferences + gap + memory + previous_plan
        ↓  (post-process: lab pairing, title override, conflict check, unit enrichment)
Professor Agent (RMP) → React frontend (calendar / 4-year grid)
```

### Run locally

Backend:

```bash
cd project/api
pip install -r requirements.txt    # shim → project/requirements.txt
cp .env.example .env   # set GEMINI_API_KEY, GOOGLE_CLIENT_ID/SECRET, etc.
uvicorn main:app --reload --port 8000 \
  --reload-dir . \
  --reload-dir ../course_planner
```

Frontend:

```bash
cd project/web
npm install
npm run dev          # opens http://localhost:5173
```

### Environment variables

| Variable | Purpose |
|----------|---------|
| `GEMINI_API_KEY` or `GOOGLE_API_KEY` | Required for live planning + embeddings (without it, embeddings fall back to deterministic hashes; planning still needs a key for Gemini JSON output) |
| `GEMINI_MODEL` | Optional override (default `gemini-2.5-flash`) |
| `SCU_PLANNER_COOKIE_KEY` | **Production:** signing key for auth cookies. Dev uses a placeholder if unset |
| `COURSE_PLANNER_DB` | Optional absolute path to SQLite DB (tests set this to a temp file) |
| `MEMORY_TOP_K`, `MEMORY_INJECT_CHAR_BUDGET`, `MEMORY_EMBED_MODEL` | Optional tuning for memory retrieval / prompt size |
| `MULTI_AGENT_PLAN` | `1` makes legacy `/api/plan` delegate to the LangGraph multi-agent engine (default off) |
| `PLANNER_REACT` | `0` disables the Planner's ReAct tool-calling loop (single-shot fallback; default on) |

Do **not** commit `.env` or `project/course_planner/data/`.

### Required local files (not in git)

Place these under `project/course_planner/` when you want full behavior (see `.gitignore`):

| File | Where to get it |
|------|-----------------|
| `View_My_Academic_Progress.xlsx` | SCU Workday → View My Academic Progress → Export |
| `SCU_Find_Course_Sections.xlsx` | SCU Workday → Find Course Sections → Export |

Without **Find Course Sections**, recommendations still render; calendar uses **Time TBD** for unmatched sections.

### Lecture + lab pairs (SCU)

For subjects like **CSEN / COEN / PHYS / CHEM / ELEN / BIOL**, a course and its **trailing-L** lab (e.g. **CSEN 194** and **CSEN 194L**) are treated as **same-quarter co-requirements** when **both** still appear in `missing_details`. The planner post-processes the model output so one half is not recommended without the other.

---

## Multi-agent planner (LangGraph)

> **Experimental** — runs alongside the default engine; opt-in via `/api/plan/v2`.

The default `/api/plan` is a single Gemini call with post-processing. A second
engine in [`project/course_planner/agents/multi_agent/`](project/course_planner/agents/multi_agent/)
re-implements planning as a **LangGraph `StateGraph`** where three roles
review each other. It runs at `POST /api/plan/v2` (legacy stays default).

```
START → Planner → Verifier ──[issues & retries<2]→ Planner      (feedback loop)
                          ├──[clean]→ Send(InstructorSelector) × N ┐  (parallel)
                          └──[no courses]──────────────────────────┤
                                                                    ▼
                                                                Assembler → END
```

### Roles (3 decision agents + 1 assembler)

| Node | Type | Decision it makes |
|------|------|-------------------|
| **Planner** | LLM, **ReAct tool-calling** | Which tools to call (and when) before proposing courses |
| **Verifier** | **deterministic** (no LLM) | Loop back to Planner / fan out / skip — after checking hallucination, time conflicts, missing labs, uncovered Core |
| **InstructorSelector** | deterministic, **parallel** | Best-rated section per course + an instructor comparison table |
| Assembler | deterministic | Merge the plan + instructor picks into the final response |

### Tools the agents can call

A registry of **9 deterministic tools** (`agents/multi_agent/tools.py`) wraps the
existing schedule/category/title/ratings utilities. The Planner exposes three to
the model via native Gemini function-calling: `search_schedule`,
`get_open_req_candidates`, `get_lab_partner`.

### LangGraph features used

- **Conditional edges** — `verifier_router` 3-way routing (loop / fan-out / skip)
- **`Send` API** — dynamic parallel fan-out: one `InstructorSelector` per course, merged via a state **reducer**
- **Checkpointing** — `InMemorySaver` (dev) / `SqliteSaver` (durable; survives restart)
- **`interrupt_before`** — human-in-the-loop: pause before committing a plan that drops a course

### HTTP endpoints

| Endpoint | Purpose |
|----------|---------|
| `POST /api/plan/v2` | Run the multi-agent engine end-to-end |
| `POST /api/plan/v2/review` | Run up to the commit step and return a **draft** for human approval (needs `thread_id`) |
| `POST /api/plan/v2/resume` | Approve a reviewed draft: resume from the checkpoint and finalize |

Set `MULTI_AGENT_PLAN=1` to make the **legacy** `POST /api/plan` transparently
delegate to the multi-agent engine (zero frontend change).

### Design notes

- **Verifier is code, not an LLM** — the rules (no conflicts, lab pairing, Core
  coverage) are deterministic, so they're cheaper and reliable. The LLM is spent
  only where creativity helps (the Planner).
- **No `langchain-google-genai`** — native Gemini function-calling inside a
  LangGraph node keeps the dependency footprint small.

### Evaluation (`agents` quality)

[`project/course_planner/evals/`](project/course_planner/evals/) scores a plan
against the domain rules with **7 deterministic scorers** (`no_hallucination`,
`no_time_conflicts`, `labs_paired`, `unit_cap`, `titles_correct`,
`open_req_coverage`, `no_injection_leak`) — **no LLM-as-judge**, so scoring is
reproducible and unit-tested (25 tests). The runner A/B-compares engines on
scenarios derived from a real transcript:

```bash
cd project/course_planner
python -m evals.run_eval --engine both          # legacy vs multi_agent A/B
python -m evals.run_eval --engine multi_agent --json
```

The LLM produces the plan; the scorers judge it deterministically.

---

## Other paths in this repository

| Path | Purpose |
|------|---------|
| [`product-vision.md`](product-vision.md) | Product vision + HMW |
| [`problem_framing_canvas.md`](problem_framing_canvas.md) | Problem Framing Canvas |
| [`architecture/architecture.md`](architecture/architecture.md) | C4 diagrams |
| [`docs/data-sources.md`](docs/data-sources.md) | Academic Progress upload vs quarterly schedule xlsx |
| [`docs/outdated-features.md`](docs/outdated-features.md) | Deprecated features (password login, Workday auto-sync, Streamlit) |
| [`project/api/`](project/api/) | FastAPI service (auth, upload, plan, four-year-plan, memory) |
| [`project/web/`](project/web/) | React + Vite frontend |

## Secrets

Do not commit `.env` files. Use `project/api/.env.example` and `project/course_planner/.env.example` as templates.
