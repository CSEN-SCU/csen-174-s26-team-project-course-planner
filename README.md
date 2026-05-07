[![Review Assignment Due Date](https://classroom.github.com/assets/deadline-readme-button-22041afd0340ce965d47ae6ef1cefeee28c7c493a6346c4f15d667ab976d596c.svg)](https://classroom.github.com/a/NfqHRKdw)

# SCU Course Planner (CSEN 174)

## Team

**SCU Course Planner** · Jason · Ismael · Joey · Jiasheng

---

## Streamlit app (`project/course_planner/`)

Python + Streamlit prototype. Students **sign in**, upload SCU **View My Academic Progress** (`.xlsx`), describe preferences in natural language, and get a **recommended next-quarter schedule** with **RateMyProfessor** enrichment and a **weekly calendar** preview (when **Find Course Sections** `.xlsx` is present).

Per-user **long-term memory** (retrieval-augmented prompts) and **follow-up chat replies** help iterative planning across sessions.

### Current implementation

| Area | Module | What it does |
|------|--------|----------------|
| Auth | `project/course_planner/auth/streamlit_auth.py`, `auth/users_db.py` | Login / register via **streamlit-authenticator**; passwords stored with **bcrypt** in SQLite |
| Database | `project/course_planner/db/connection.py`, `db/migrate.py`, `db/schema.sql` | SQLite at `project/course_planner/data/app.db` (gitignored): `users`, `memory_items`, **sqlite-vec** `memory_vec` for embeddings |
| Memory (RAG) | `project/course_planner/agents/memory_agent.py` | **Gemini `text-embedding-004`** (fallback hash vectors if no API key); `write` / `retrieve` / list / delete — **scoped by `user_id`** |
| Orchestration | `project/course_planner/agents/orchestrator.py` | `plan_for_user`: retrieve memory → **planning_agent** → write summary; **PII redaction** on retrieved snippets before the LLM |
| Planning | `project/course_planner/agents/planning_agent.py` | **Gemini** structured JSON: `recommended`, `total_units`, `advice`, **`assistant_reply`**. **Lecture+lab pairs** (e.g. CSEN 194 + CSEN 194L) when both appear in the gap; retries / fallback models; **`meta` / `warnings` / per-course `alternatives`** |
| Requirement parsing | `project/course_planner/main.py` → `utils/academic_progress_xlsx.py` | Parses DegreeWorks export locally; builds `missing_details` |
| Professor ratings | `project/course_planner/agents/professor_agent.py` | RateMyProfessor GraphQL (parallel); aligns to Find Course instructors when possible |
| Calendar | `project/course_planner/main.py` | Mon–Fri columns from **Meeting Patterns** in Find Course Sections `.xlsx` |
| UI | `project/course_planner/main.py` | Login gate; sidebar **My memory**; chat bubbles for user message + **`assistant_reply`** |

### Tests

From the repository root (with the repo `.venv`):

```bash
cd project/course_planner
../../.venv/bin/python -m pytest tests/
```

### Architecture (high level)

```
Academic Progress (.xlsx)
        ↓
Requirement Parser (local)
        ↓
Orchestrator.plan_for_user  ←  SQLite memory (retrieve / write)
        ↓
Planning Agent (Gemini)     ←  preferences + gap + memory snippets + optional previous plan
        ↓  (post-process: lecture/lab co-reqs when partner still in gap)
Professor Agent (RMP)
        ↓
Calendar UI (Streamlit)
```

**Roadmap / optional**

| Piece | Status | Notes |
|-------|--------|-------|
| Requirement Agent (LLM PDF) | Implemented, not wired to main UI | `agents/requirement_agent.py` |
| Email Agent | Planned | Human-in-the-loop draft to instructor |

### Run locally

```bash
cd project/course_planner
pip install -r requirements.txt
cp .env.example .env   # set GEMINI_API_KEY (or GOOGLE_API_KEY)
streamlit run main.py
```

Open the URL Streamlit prints (default **http://localhost:8501**).

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
| [`project/api/`](project/api/) | TypeScript Express + Prisma (`bronco-plan-api`) |
| [`project/web/`](project/web/) | React + Vite frontend |
| [`prototypes/`](prototypes/) | Teammate divergent prototypes |

## Secrets

Do not commit `.env` files. Use `project/course_planner/.env.example` or `prototypes/<name>/.env.example` as templates.
