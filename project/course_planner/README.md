# SCU Course Planner — `project/course_planner/`

This directory is a **Python package** containing shared agents,
SQLite + sqlite-vec schema, auth helpers, and xlsx parsers consumed
by the FastAPI service in [`../api/`](../api/) and (indirectly via
that service) the React frontend in [`../web/`](../web/).

Read the repo-root **[`README.md`](../../README.md)** first for the
full product description, architecture, and run instructions.

---

## Quick start (backend only)

```bash
# From repo root
cd project/api
pip install -r requirements.txt -r ../course_planner/requirements.txt
cp .env.example .env   # GEMINI_API_KEY, GOOGLE_CLIENT_ID/SECRET, ...
uvicorn main:app --reload --port 8000 \
  --reload-dir . \
  --reload-dir ../course_planner
```

Tests live one level up (`project/tests/`):

```bash
cd project
python3 -m pytest tests/
```

---

## Team

Jason · Ismael · Joey · Jiasheng
