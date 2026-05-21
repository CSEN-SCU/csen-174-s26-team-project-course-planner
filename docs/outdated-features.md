# Outdated or deprecated product features

This document tracks capabilities that are **no longer part of the intended v1 product** but may still exist in code, specs, or older docs. Use it when cleaning up kanban items or updating README / AGENTS.

**Last updated:** 2026-05-21 (team decision: Google-only sign-in; no Workday auto-sync)

**Planner fixes (2026-05-21):** Completed-course filtering, unit enrichment, and lab lecture pairing were added in `planning_agent.py` — see git history for `test_planning_postprocess.py`.

---

## 1. Username / password sign-in

| Status | **Removed from UI** (2026-05-21). Backend endpoints may still exist. |
|--------|------------------------------------------------------------------------|

### What it was

- Log in / Register tabs with username + password in the left sidebar (Streamlit era) and, briefly, on the React home page (“Sign in with username instead”).
- API: `POST /api/auth/login`, `POST /api/auth/register`.

### Current product direction

- **Google OAuth only** on the landing page (`Continue with Google`).

### Where it still appears (cleanup candidates)

| Location | What it says |
|----------|----------------|
| `project/api/routers/auth.py` | `login`, `register` routes |
| `project/course_planner/auth/users_db.py` | SQLite users + bcrypt passwords |
| `project/course_planner/specs/01-user-authentication.md` | Full spec for username/password tabs (Streamlit-era) |
| `project/course_planner/AGENTS.md` | “login/register via streamlit-authenticator” |
| `docs/sprint-1-testing.md` | Password hashing / salt tests (still valid for **stored** accounts if any exist) |

### Sources (how we know it was planned)

- **Conversation / product:** User request (2026-05-21) to drop username/password from the home page.
- **Repo history:** `LeftPanel.tsx` previously had login/register tabs; `UsernameAuthPanel.tsx` was added for the landing page then removed.
- **Spec:** `project/course_planner/specs/01-user-authentication.md` (behaviors 3–7 describe registration and login tabs).

---

## 2. Workday Playwright auto-sync (“Sync from Workday”)

| Status | **Deprecated for v1** — UI copy removed from home page; chat UI may still expose sync. |
|--------|----------------------------------------------------------------------------------------|

### What it was

- Button in the chat panel to scrape academic progress from Workday via Playwright (`POST /api/workday/sync`, poll `/api/workday/status/{job_id}`).
- Alternative to uploading an `.xlsx` / `.xlsm` Academic Progress export.

### Current product direction

- Students **upload** the Workday export file (manual export). See **Academic Progress Export Tutorial** in the footer (`#/academic-progress-export-tutorial`).
- Home page no longer says “sync Workday” under the Google button.

### Where it still appears (cleanup candidates)

| Location | What it says |
|----------|----------------|
| `project/web/src/components/ChatPanel.tsx` | Workday sync button, status bar, messages (“sync directly from Workday”) |
| `project/web/src/api/client.ts` | `startWorkdaySync`, `pollWorkdayStatus` |
| `project/api/routers/workday.py` | Sync + status endpoints |
| `project/api/main.py` | `workday` router mounted |
| `project/api/middleware/rate_limit.py` | `workday_sync` rate limits |
| `HANDOFF.md` §0 env | `SCU_WORKDAY_URL` marked **STALE**; §1 data flow lists “Workday Playwright sync” |
| `docs/sprint-1-retro.md` | Jiasheng contribution: “Workday auto-sync via Playwright” |
| `README.md` | May reference Workday sync (verify when editing README) |

### Sources

- **User decision (2026-05-21):** “we are not doing that anymore” (Workday sync); keep tagline that mentions avoiding the “Workday maze” (positioning only).
- **HANDOFF.md:** `SCU_WORKDAY_URL=...  # STALE — see #W below` and architecture diagram branch `(or Workday Playwright sync)`.
- **Sprint retro:** `docs/sprint-1-retro.md` — shipped Workday auto-sync in Sprint 1.
- **AGENTS.md:** Does not mandate Workday sync; R3/R6 focus on memory and calendar UX.

### Related (still valid)

- **Manual Workday export tutorial** — `AcademicProgressExportTutorialPage.tsx` + images under `project/web/src/img/Workday_tutorial_*.png`. This is **not** deprecated; it teaches export, not browser automation.
- Copy “`.xlsx or .xlsm export from Workday`” in `ChatPanel.tsx` — accurate for upload flow.

---

## 3. Streamlit app (original stack)

| Status | **Superseded** by React + FastAPI (`project/web`, `project/api`). |
|--------|---------------------------------------------------------------------|

### Sources

- `project/course_planner/AGENTS.md` — `streamlit run main.py`, Streamlit theme.
- `project/course_planner/main.py` — legacy entry (if still present).

---

## 4. Stale brand red in CSS (fixed 2026-05-21)

| Status | **Updated** in `project/web/src/index.css`. |

Previous UI used `#c8102e` / `#8b0000`. Official references:

- Santa Clara red: `#A32035`
- Bronco red: `#862633` (footer background)

---

## Suggested cleanup order (kanban-friendly)

1. Remove Workday sync UI + API (or gate behind env flag) — largest dead path.
2. Remove or document-only `POST /auth/login` and `/auth/register` if no non-Google users needed.
3. Archive or mark `specs/01-user-authentication.md` as Streamlit-legacy.
4. Update `HANDOFF.md` / `README.md` data-flow diagram to upload-only.

---

## How to keep this doc current

When deprecating a feature:

1. Add a row under the right section with **status**, **sources** (PR, retro, user chat, spec path).
2. List **files to change** before deleting code.
3. Note what **replaces** it for students (e.g. upload + tutorial link).
