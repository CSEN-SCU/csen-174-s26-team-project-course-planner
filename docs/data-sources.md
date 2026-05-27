# Data sources for SCU Course Planner

## What students upload (in the app)

**Academic Progress export** — Workday “View My Academic Progress” saved as `.xlsx` / `.xlsm`.

- Uploaded in the chat panel (paperclip).
- Parsed into:
  - **`missing_details`** — requirements still marked *Not Satisfied* (what the planner should fill).
  - **`parsed_rows`** — course history rows (Satisfied / In Progress) used to avoid recommending classes already taken.

This is **not** a full university transcript PDF; it is the same Excel export students use in DegreeWorks/Workday.

## What the team updates each quarter (not uploaded in the UI)

**Next-term course list** — `project/course_planner/SCU_Find_Course_Sections.xlsx` (or `scu_find_course.xlsx`).

- Replaced manually when the team publishes the new SCU “Find Course Sections” export.
- Drives which courses exist next term, meeting times, titles, Core/GE tags, and instructor sections.
- Deployed with the **API** service (file lives in the backend repo tree).

There is currently **no** student-facing upload for this file; updating it is an operator/deploy step.

**Major requirements & prerequisites** — `project/course_planner/data/majors/`

- One Markdown file per popular major: `data/majors/<major_id>.md` (required courses + each course’s bulletin prerequisites).
- Manifest: `data/majors/index.json`. Legacy compact index: `data/major_requirements.json`.
- Refresh all configured majors: `cd project/course_planner && python3 scripts/scrape_major_requirements.py`
- Single major: `python3 scripts/scrape_major_requirements.py --major csen --major ecen`
- Planning agents load `data/majors/<detected_major>.md` into the prompt when Workday text matches that major.

## Related docs

- [`docs/outdated-features.md`](outdated-features.md) — removed Workday auto-sync, deprecated username/password login, etc.
- [`AGENTS.md`](../AGENTS.md) — domain rules (lab pairing, units, etc.)
