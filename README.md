# SCU Course Planner

## Team

**SCU Course Planner** · Jason · Ismael · Joey · Jiasheng

---

SCU Course Planner is a web app for Santa Clara University students. The website allows students to upload their Academic Progress Report in order to receive tailored course recommendations to aid students in planning their upcoming schedules. Next, students can manually add and remove classes to refine their schedule and save it for future reference. SCU Course Planner also visually lays out academic progress in a Four-Year Plan table, where students can then receive tailored Four-Year Plan recommendations.

## Demo Links

Read the technical report [Here](https://github.com/CSEN-SCU/csen-174-s26-team-project-course-planner/blob/main/docs/technical-report.md)

View a live demo of SCU Course Planner [Here](https://csen-174-s26-team-project-course-planner.onrender.com/)

Watch a demo video of SCU Course Planner [Here](https://youtu.be/tVj_4x3yKEU)

## Run Locally

**Backend**:

```bash
cd project/api
pip install -r requirements.txt -r ../course_planner/requirements.txt
cp .env.example .env   # Manually set variables within file with your own values
uvicorn main:app --reload --port 8000 \
  --reload-dir . \
  --reload-dir ../course_planner
```

**Frontend**:

```bash
cd project/web
npm install
npm run dev          # http://localhost:5173
```

Open **http://localhost:5173** in your browser (API at **http://localhost:8000**)


## Project Architecture

```
Manual Academic Progress Report uploaded by user (.xlsx)
        ↓
Requirement Parser → parsed_rows + missing_details
        ↓
[FastAPI /api/plan or /api/four-year-plan]
        ↓
Orchestrator.plan_for_user  ←  SQLite memory (retrieve / write)
        ↓
Planning Agent (Gemini API)     ←  preferences + gap + memory + previous_plan
        ↓  (post-process: lab pairing, title override, conflict check)
Professor Agent (RMP) → React frontend (calendar / 4-year grid)
```

## Prerequisites

| Tool | Version | Notes |
|------|---------|-------|
| Python | **3.12** | Matches GitHub CI, used for backend |
| Node.js | **≥ 20.12** | Vite frontend |
| npm | Bundled with Node | Installs frontend dependencies |
| Gemini API Key | N/A | Used for Gemini API calls |
| Google OAuth | 2.0 | Used for account login |

A virtual environment is recommended for the backend
(`python3 -m venv .venv && source .venv/bin/activate` before `pip install`).

## Environment variables

The following variables are stored and set in `.env`

| Variable | Purpose |
|----------|---------|
| `GEMINI_API_KEY` or `GOOGLE_API_KEY` | Used for Gemini API calls |
| `GEMINI_MODEL` | Optional, overrides default `gemini-2.5-flash` |
| `SCU_PLANNER_COOKIE_KEY` | **Production:** signing key for auth cookies. Dev uses a placeholder if unset |
| `COURSE_PLANNER_DB` | Optional absolute path to SQLite DB (tests set this to a temp file) |
| `MEMORY_TOP_K`, `MEMORY_INJECT_CHAR_BUDGET`, `MEMORY_EMBED_MODEL` | Optional tuning for memory retrieval / prompt size |
| `PLANNER_REACT` | `0` disables the Planner's ReAct tool-calling loop (single-shot fallback; default on) |

Do not commit `.env` files. Use `project/course_planner/.env.example` or `prototypes/<name>/.env.example` as templates.

## Required Workday files

Place these under `project/course_planner/` for full functionality when run locally.

| File | Where to get it |
|------|-----------------|
| `SCU_Find_Course_Sections.xlsx` | SCU Workday → Find Course Sections → Export |

Without **Find Course Sections**, recommendations still render; calendar uses **Time TBD** for unmatched sections.


## Paths in this repository

| Path | Description |
|------|---------|
| [`docs`](docs) | Documentation of repo |
| [`architecture`](architecture) | Architecture of SCU Course Planner |
| [`project`](project) | SCU Course Planner software |
| [`.cursor`](.cursor) | Contains skills used by Cursor |
| [`.github`](.github) | Contains GitHub CI configuration |

