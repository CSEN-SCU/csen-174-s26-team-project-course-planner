# Jiasheng — prototype

End-to-end flow: upload **Workday “View My Academic Progress”** (`.xlsx`), paste a **public major requirements URL** (e.g. SCU engineering pages), and get a **ranked list of selectable courses** for the chosen term using the bundled **course sections** export (`SCU_Find_Course_Sections.xlsx`) for schedules, tags, and instructors.

Compared with static browsing, this emphasizes **progress-driven gaps**, **major requirement parsing**, and **transparent ordering** (missing major courses first, then tag-matched electives where applicable).

Path: `course-planner/prototypes/jiasheng/`

## Stack (course requirements)

- **Front end**: Jinja2 templates + static JS — landing (`/`) and app (`/app`)
- **Back end**: FastAPI (`app/main.py`)
- **Database**: SQLite + SQLAlchemy (default `data/app.db`)
- **AI (optional)**: Gemini and/or OpenAI for structured parsing and rationale text; set keys in environment only (never commit keys)

### Using Gemini (optional)

```bash
export GEMINI_API_KEY="your-key"
export AI_PROVIDER="gemini"   # or auto (prefers Gemini when key is set)
# export GEMINI_MODEL="gemini-2.0-flash"
```

Keys belong in **server environment variables** or a local `.env` (gitignored). Do not put secrets in the repo or front end.

## Run locally

From `course-planner/prototypes/jiasheng/`:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Optional: avoid macOS permission issues writing bytecode
export PYTHONPYCACHEPREFIX="$(pwd)/.pycache_dir"

python -m uvicorn app.main:app --reload --port 8010
```

### One-command dev server (recommended)

```bash
./run_dev.sh
```

Custom port:

```bash
PORT=8011 ./run_dev.sh
```

Open in the browser:

- `http://127.0.0.1:8010/` — landing page
- `http://127.0.0.1:8010/app` — app (upload Academic Progress `.xlsx`, major requirements URL, generate)

## API (for demos)

- `POST /api/upload_progress` — upload Academic Progress `.xlsx`; returns `file_id`
- `GET /api/plan_from_progress?url=...&term=...&file_id=...` — build recommendations from uploaded file + major requirements page
- `GET /api/major_requirements?url=...` — fetch and parse a public major requirements page
- `POST /api/plan` — legacy transcript-based plan (if used)
- `GET /api/session/{id}` — load a stored session and recommendations

## Data files

- `SCU_Find_Course_Sections.xlsx` — term offerings (sections, instructors, tags); used as the selectable course pool when present.
- Copy `.env.example` to `.env` locally if you use environment-based API keys.
