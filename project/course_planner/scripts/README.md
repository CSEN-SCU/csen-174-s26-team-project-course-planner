# `project/course_planner/scripts/` — utility scripts

| Script | Purpose |
|--------|---------|
| [`scrape_rmp_ratings.py`](scrape_rmp_ratings.py) | One-time RateMyProfessor scrape → `data/instructor_ratings.csv`. |
| `workday_pull_progress.py` | **Workday auto-pull (branch prototype)** — pull a student's *View My Academic Progress* export. |
| `workday_pull_sections.py` | **Workday auto-pull (branch prototype)** — pull the shared *Find Course Sections* catalog (admin). |

---

## Workday auto-pull (branch prototype)

Two **headed** Playwright scripts that re-add automated Workday pulls **without
ever handling SCU credentials**. A real browser window opens; **you** complete
SSO + Duo by hand; the script automates only the steps *after* login
(navigate → click **Export to Excel** → capture the download). A persistent,
gitignored browser profile keeps you logged in between runs.

History: an earlier headless, credential-injecting `POST /api/workday/sync`
scraper was removed on 2026-05-23 (see [`docs/outdated-features.md`](../../../docs/outdated-features.md)).
`playwright` was kept in `project/requirements.txt` so this safer approach could
be re-attempted on a branch.

### Prototype boundary — read first

- **Trigger is a CLI command, not an in-app button.** A web page cannot launch a
  local browser, so the student/admin runs the script from a terminal. (The
  student still logs in themselves — the script just opens the browser for them.)
- **Zero credential handling.** We never see, type, or store SCU passwords. The
  only persisted state is a local login profile at
  `project/course_planner/.workday_profile/`, which is **gitignored**.
- **Productionization path = a browser extension** (Chrome/MV3) running in the
  student's existing Workday tab. That is **future work, out of scope here.**

### Install (from zero)

```bash
# From the repo root — installs deps incl. playwright==1.60.0
pip install -r project/requirements.txt

# One-time: download the Chromium browser Playwright drives
playwright install chromium
```

A virtualenv is recommended (see the root [`README.md`](../../../README.md)
"Prerequisites" — Python 3.12). Use the **same interpreter** you run the API
with, so the in-process xlsx validation imports resolve.

### Usage

Run from `project/course_planner/`:

```bash
cd project/course_planner
```

#### 1. Academic progress — per student

```bash
# Default: POST the export to a running API as this user (same path as the
# paperclip upload). The API must be up at http://localhost:8000.
python scripts/workday_pull_progress.py --user-id <USER_ID>

# Alternative: just write the .xlsx to disk, don't upload.
python scripts/workday_pull_progress.py --save ./View_My_Academic_Progress.xlsx
```

A browser opens → log in and approve Duo. The script then exports
*View My Academic Progress*, validates the parsed rows in-process (and aborts
loudly if they come back empty — a sign Workday's layout changed), and either
POSTs the bytes to `/api/upload/transcript` or saves them per `--save`.

#### 2. Course sections — admin

```bash
python scripts/workday_pull_sections.py
```

Opens a browser → log in. The script exports *Find Course Sections* and
**atomically overwrites** `project/course_planner/SCU_Find_Course_Sections.xlsx`
(the shared catalog — identical for every student, not pulled per-user). To run
it "on a schedule," wrap it in cron/launchd; note it still needs a valid session
(the persistent profile) and a human re-login whenever that session expires.

#### After pulling course sections: refresh the API

`GET /api/courses` and the schedule indexes are cached (`lru_cache`), so a freshly
written xlsx is **not** served until the caches clear. Either:

- **Restart the API** (prototype default), or
- `POST /api/courses/refresh` — if/once that cache-clearing endpoint is added.

### The login profile (security)

- The first run creates `project/course_planner/.workday_profile/`, a persistent
  Chromium profile holding your Workday cookies/session so you don't re-login
  every time.
- It is **gitignored** — cookies/session/credentials must never be committed.
  After any run, confirm `git status` shows **no** profile, cookie, or `.tmp`
  download files.
- Delete the directory to force a fresh login.
