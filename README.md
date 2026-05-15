[![Review Assignment Due Date](https://classroom.github.com/assets/deadline-readme-button-22041afd0340ce965d47ae6ef1cefeee28c7c493a6346c4f15d667ab976d596c.svg)](https://classroom.github.com/a/NfqHRKdw)

# SCU Course Planner (CSEN 174)

## Team

**SCU Course Planner** · Jason · Ismael · Joey · Jiasheng

---

## SCU Course Planner

A web app for Santa Clara University students. Upload SCU **View My
Academic Progress** (`.xlsx`) or sync directly from Workday, describe
preferences in natural language, and get a **recommended next-quarter
schedule** and **multi-quarter graduation plan** with **RateMyProfessor**
enrichment and a **weekly calendar** preview (when **Find Course
Sections** `.xlsx` is present). Per-user **long-term memory** (RAG)
and **follow-up chat replies** support iterative planning across
sessions.

Two services compose the app:

| Path | Stack | Role |
|------|-------|------|
| [`project/api/`](project/api/) | FastAPI + Python agents | REST API for auth, transcript upload, plan generation, four-year plan, Workday sync, memory CRUD |
| [`project/web/`](project/web/) | React + Vite + Tailwind | SPA: login + chat + calendar + 4-year grid |
| [`project/course_planner/`](project/course_planner/) | Python package | Shared **agents**, **SQLite + sqlite-vec**, **auth/users_db**, and **xlsx parsers** used by the FastAPI service |

### Current implementation

| Area | Module | What it does |
|------|--------|----------------|
| Auth | `project/api/routers/auth.py`, `project/course_planner/auth/users_db.py`, `auth/google_oauth.py` | Username/password (bcrypt + SQLite) plus Google OAuth |
| Database | `project/course_planner/db/connection.py`, `db/migrate.py`, `db/schema.sql` | SQLite at `project/course_planner/data/app.db` (gitignored): `users`, `memory_items`, **sqlite-vec** `memory_vec` for embeddings |
| Memory (RAG) | `project/course_planner/agents/memory_agent.py` | **Gemini `text-embedding-004`** (fallback hash vectors if no API key); `write` / `retrieve` / list / delete — **scoped by `user_id`** |
| Orchestration | `project/course_planner/agents/orchestrator.py` | `plan_for_user`: retrieve memory → **planning_agent** → write summary; **PII redaction** on retrieved snippets before the LLM |
| Planning | `project/course_planner/agents/planning_agent.py` | **Gemini** structured JSON: `recommended`, `total_units`, `advice`, **`assistant_reply`**. **Lecture+lab pairs** (e.g. CSEN 194 + CSEN 194L) when both appear in the gap; retries / fallback models; **`meta` / `warnings` / per-course `alternatives`**. Prompt-injection sanitiser on user text |
| Four-year plan | `project/course_planner/agents/four_year_planning_agent.py` | Multi-quarter graduation grid; surfaces open Core/GE candidates via Course-Tags index; typed `EmptyPlanError` / `InconsistentPlanError` |
| Requirement parsing | `project/course_planner/utils/academic_progress_xlsx.py` | Parses DegreeWorks export; builds `missing_details` and `parsed_rows` |
| Workday sync | `project/api/routers/workday.py`, `project/course_planner/utils/workday_scraper.py` | Playwright-driven export with search-bar fallback; URL allowlist + error scrubbing |
| Professor ratings | `project/course_planner/agents/professor_agent.py` | RateMyProfessor GraphQL (parallel); aligns to Find Course instructors when possible |
| Rate limiting | `project/api/middleware/rate_limit.py` | Per-IP, per-user, per-user-concurrency token bucket on `/api/plan`, `/api/four-year-plan`, `/api/workday/sync` |
| Calendar + 4-year UI | `project/web/src/components/CalendarView.tsx`, `FourYearPlanView.tsx` | Mon–Fri weekly grid plus 4-year graduation grid overlaying completed transcript history with AI recommendations |

### Tests

From `project/`:

```bash
cd project
python3 -m pytest tests/
```

### Architecture (high level)

```
Academic Progress (.xlsx)  ──or──>  Workday (Playwright sync)
        ↓
Requirement Parser → missing_details + parsed_rows
        ↓
[FastAPI /api/plan or /api/four-year-plan]
        ↓
Orchestrator.plan_for_user  ←  SQLite memory (retrieve / write)
        ↓
Planning Agent (Gemini)     ←  preferences + gap + memory + previous_plan
        ↓  (post-process: lab pairing, title override, conflict check)
Professor Agent (RMP) → React frontend (calendar / 4-year grid)
```

### Run locally

Backend:

```bash
cd project/api
pip install -r requirements.txt -r ../course_planner/requirements.txt
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

## Other paths in this repository

| Path | Purpose |
|------|---------|
| [`product-vision.md`](product-vision.md) | Product vision + HMW |
| [`problem_framing_canvas.md`](problem_framing_canvas.md) | Problem Framing Canvas |
| [`architecture/architecture.md`](architecture/architecture.md) | C4 diagrams |
| [`project/api/`](project/api/) | FastAPI service (auth, plan, four-year-plan, Workday sync, memory) |
| [`project/web/`](project/web/) | React + Vite frontend |
| [`prototypes/`](prototypes/) | Teammate divergent prototypes |

## Secrets

Do not commit `.env` files. Use `project/course_planner/.env.example` or `prototypes/<name>/.env.example` as templates.
