# AGENTS.md — SCU Course Planner

## Run application

Two services. From the repo root:

```bash
# Backend
cd project/api
uvicorn main:app --reload --port 8000 \
  --reload-dir . \
  --reload-dir ../course_planner
```

```bash
# Frontend (separate terminal)
cd project/web
npm run dev          # http://localhost:5173
```

## Run tests
```bash
cd project
npm ci
npm test
```

Vitest config: `project/vitest.config.ts`; tests live in `project/tests/`.

Python (FastAPI + agents):
```bash
cd project
python -m pytest tests/
```

## Install dependencies
```bash
cd project/api
pip install -r requirements.txt -r ../course_planner/requirements.txt
```
Voice transcription uses the `SpeechRecognition` package and **Google’s speech API over the network** when you click **Transcribe recording → preferences**.

## Key environment variables
- `GEMINI_API_KEY` or `GOOGLE_API_KEY` — required for planning agent, curriculum PDF gap analysis, and embeddings
- `GEMINI_MODEL` — optional, defaults to `gemini-2.5-flash`
- `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` — Google OAuth web client (optional; username/password sign-in still works without them)
- `GOOGLE_OAUTH_REDIRECT_URI` — must match the Authorized redirect URI in Google Cloud Console
- `SCU_PLANNER_COOKIE_KEY` — signs OAuth state + handoff token
- `SCU_WORKDAY_URL` — the Workday task URL for View My Academic Progress (used by the Playwright scraper)
- `FRONTEND_BASE_URL` — where the API redirects the browser after Google sign-in (default `http://localhost:5173`)
- `COURSE_PLANNER_DB` — optional path to SQLite DB
- `MEMORY_COMPACTION_TRIGGER_BYTES` — byte threshold before memory file is compacted (default 512KB)

## Project layout
- `agents/` — planning, four-year planning, professor, memory, orchestrator agents
- `auth/` — `users_db.py` (SQLite-backed users + bcrypt), `google_oauth.py`, `oauth_state.py`
- `db/` — SQLite connection, schema, migrations
- `utils/` — xlsx parsers, schedule index, Workday scraper, helpers
- `specs/` — Ralph specs (source of truth for behavior)
- `data/` — local SQLite DB + per-user memory files (gitignored)

## Required local files (not in git)
- `project/course_planner/View_My_Academic_Progress.xlsx`
- `project/course_planner/SCU_Find_Course_Sections.xlsx`

## Important notes
- Memory is scoped per user — one Markdown file per user (default ``data/memory/<user_id>.md``; override with ``COURSE_PLANNER_MEMORY_DIR``)
- Each file lists machine-delimited blocks (JSON header + body); safe to edit body text in an editor
- Memory rolling compaction runs after each successful ``write`` when total body bytes exceed ``MEMORY_COMPACTION_TRIGGER_BYTES`` (see ``agents/memory_agent.py`` and spec ``05-per-user-embedding-memory.md``)
- Gemini embeddings are used for retrieval; no SQLite vector store
- RateMyProfessor client is required — all course recommendations must include professor ratings
- Thursday meeting pattern: ``Th`` or ``R`` maps to the Thursday column (``T`` is Tuesday; contiguous strings like ``MTTh`` are tokenized greedily for ``Th``).