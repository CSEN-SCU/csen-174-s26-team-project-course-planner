# Outdated or deprecated product features

This document tracks capabilities that are **no longer part of the intended v1 product** but may still exist in code, specs, or older docs. Use it when cleaning up kanban items or updating README / AGENTS.

**Last updated:** 2026-05-23 (Google-only sign-in; manual Academic Progress upload; Workday auto-sync out of v1 scope)

---

## 1. Username / password sign-in

| Status | **Removed** from UI and API (2026-05-21). |
|--------|-------------------------------------------|

### What it was

- Log in / Register tabs with username + password (Streamlit era and early React).
- API: `POST /api/auth/login`, `POST /api/auth/register`.

### Current product direction

- **Google OAuth only** on the landing page (`Continue with Google`).
- SQLite `users` table stores OAuth-linked identities only (no bcrypt passwords).

### Historical sources

- `UsernameAuthPanel.tsx` removed; `specs/01-user-authentication.md` removed.
- See git history around `f27fe3b` / `6fffaa8`.

---

## 2. Workday Playwright auto-sync (“Sync from Workday”)

| Status | **Out of v1 scope** — not shipped. Manual Academic Progress Excel upload is the supported path. |
|--------|------------------------------------------------------------------------------------------------|

### What it was

- Button to scrape academic progress from Workday via Playwright (`POST /api/workday/sync`, poll status).
- Alternative to uploading an `.xlsx` / `.xlsm` Academic Progress export.

### Current product direction

- Students **upload** the Workday export file. See **Academic Progress Export Tutorial** in the footer (`#/academic-progress-export-tutorial`).
- **`playwright` remains in `project/requirements.txt`** so a teammate can experiment with scraper code in a branch without re-adding the dependency; the live app does not expose sync endpoints today.

### Removed from production (2026-05)

| Location | What was removed |
|----------|------------------|
| `project/web/src/components/ChatPanel.tsx` | Workday sync button and polling |
| `project/web/src/api/client.ts` | `startWorkdaySync`, `pollWorkdayStatus` |
| `project/api/routers/workday.py` | Sync + status endpoints |
| `project/course_planner/utils/workday_scraper.py` | Playwright scraper implementation |

### Related (still valid — not deprecated)

- **Manual Workday export tutorial** — `AcademicProgressExportTutorialPage.tsx` + `Workday_tutorial_*.png`.
- Copy “`.xlsx or .xlsm export from Workday`” in the upload UI.

---

## 3. Streamlit app (original stack)

| Status | **Superseded** by React + FastAPI (`project/web`, `project/api`). |
|--------|---------------------------------------------------------------------|

Removed in git history (`696097a`): `main.py`, `streamlit_auth.py`, `scu_theme.py`, Streamlit-only tests.

---

## 4. Stale brand red in CSS (fixed 2026-05-21)

| Status | **Updated** in `project/web/src/index.css`. |

Santa Clara red: `#A32035` · Bronco red (footer): `#862633`

---

## Suggested cleanup order (kanban-friendly)

1. ~~Workday sync UI + API~~ — removed from v1; keep manual export tutorial.
2. ~~Password login~~ — removed; Google OAuth only.
3. Consolidate tests under `project/tests/` (done 2026-05-23).
4. Keep README / AGENTS / HANDOFF aligned with FastAPI + React stack.

---

## How to keep this doc current

When deprecating a feature:

1. Add a row with **status**, **sources** (PR, retro, user chat, spec path).
2. List **files to change** before deleting code.
3. Note what **replaces** it for students (e.g. upload + tutorial link).
