# Manual Course Browser — Agent Implementation Plan

**Goal:** Let students build a quarter schedule **without** uploading Academic Progress, using a Workday-style “Find Course Sections” experience backed by `SCU_Find_Course_Sections.xlsx` on the server.

**Audience:** Cursor agent implementing this feature. Read `AGENTS.md` domain rules (especially **R1 lab pairing**) before coding.

---

## Progress tracker (update every PR / session)

| Phase | Status | Notes |
|-------|--------|-------|
| **0** Setup | `[x]` Complete | Schedule xlsx for local dev; AGENTS R1 noted |
| **1** Backend (sections API, overlap helper) | `[x]` Complete | `GET /api/catalog/sections`, overlap helper, tests |
| **2** Frontend core (browser, New Plan / slot modals) | `[x]` Complete | CourseBrowser, PlanStartModal, SlotActionModal, App wiring |
| **3** Filters (subject, days, times, tags) | `[x]` Complete | In CourseBrowser sidebar + API query params |
| **4** Polish & tests | `[~]` In progress | Vitest updated; anchored calendar badge done; HANDOFF pending |
| **5** v1.1 (open requirements filter, ★, 1hr grid) | `[ ]` Not started | |

**Last updated:** 2026-05-26 — initial v1 implementation (Cursor agent)

### How to mark progress (required for all agents)

1. **Use Markdown checkboxes** in this file: `- [ ]` = not done, `- [x]` = done.
2. When you **finish a phase** (or a major subsection), change every checkbox in that block to `[x]`.
3. Update the **Progress tracker** table above: replace `[ ]` with `[x]` in the Status column and add a one-line note (e.g. “merged PR #42”).
4. Set **Last updated** to today’s date.
5. If you only complete **part** of a phase, leave the phase as `[~]` in the table and note what’s left in Notes.
6. **Do not** delete checklist items; only check them off or add sub-bullets under Notes.
7. Commit the plan file **in the same PR** as the code when possible so `main` always reflects reality.

**Quick status legend:** `[ ]` not started · `[~]` in progress · `[x]` complete

---

## 1. Executive summary (plain English)

Today the app has a small **“+ Add course”** search box that only works after you type a query; it does not show filters or a full catalog table. The schedule data file **already includes requirement tags** (ELSJ, RTC 1–3, C&I 1–3, etc.) in a `Course Tags` column — **no change needed to the xlsx for basic filtering**.

This plan adds a **Course Browser** panel: search bar + filter sidebar (subject, days, times, requirement tags) + results table (like Workday). Picking a row adds that course (and its lab partner when applicable) to the calendar **even if no transcript was uploaded**. AI chat can still ask for a transcript for *automated* planning; manual building is independent.

**New flows (product ask):**

1. **New Plan** → student chooses **manual course search** or **AI-recommended schedule** (not only chat).
2. **Calendar click** → student chooses **browse courses in that time** or **AI suggestions**; show every section whose meeting **overlaps the clicked time cell** (not only courses that start inside a narrow window).

---

## 2. Data source confirmation (verified against user files)

### 2.1 `SCU_Find_Course_Sections.xlsx` (backend catalog)

| Column | Use in browser |
|--------|----------------|
| `Course Section` | Display + parse subject/number/section (e.g. `CSEN 174-1 - …`) |
| `Course Subject` | **Filter:** subject facet (Accounting, CSEN, Music, …) — 56 values in sample |
| `Course Number` | Sort / display |
| `Section Number` | Distinguish sections of same course |
| `Section Status` | Optional badge (Open / Waitlist / Closed) |
| `Enrolled/Capacity` | Optional display |
| `All Instructors` | Display; future: tie to RMP ratings (R5) |
| `Units` | Display + plan unit total |
| `Meeting Patterns` | **Filter:** days + time (`M W F \| 8:00 AM - 9:05 AM`) — already parsed in `scu_course_schedule_xlsx.py` |
| `Locations` | Display |
| `Course Tags` | **Filter:** requirement tags (see below) |
| `Instructional Format` / `Delivery Mode` | **Out of scope** unless product asks later |

**Course Tags format (multi-line per row):**

```
Core Explorations :: RTC 3 | Religion, Theology and Culture 3
Core Integrations :: ELSJ | Experiential Learning for Social Justice
```

Parser already exists: `_parse_course_tag_codes()` and `load_category_course_index()` in  
`project/course_planner/utils/scu_course_schedule_xlsx.py`.

**Sample tag short codes present in data:** `RTC 1`, `RTC 2`, `RTC 3`, `C&I 1`, `C&I 3`, `ELSJ`, `Arts`, `Social Science`, `Natural Science`, `Applied Ethics`, `Diversity: US Perspectives`, major-specific tags (`LSB Core :: …`), Pathways tags, etc.

**Note:** Derive the filter checklist from the xlsx at runtime (or via a one-time facet endpoint), **do not hardcode** only RTC/C&I/ELSJ — some codes appear under multiple spellings (`Cultures and Ideas 3` vs `C&I 3`). Matching should use the same normalization as `load_category_course_index` (lowercase keys).

### 2.2 `View_My_Academic_Progress.xlsx` (optional enhancement)

Requirement rows look like:

- `Core: ENGR: C&I 3`
- `Computer Science and Engineering Major: Educational Enrichment - Courses`

These names **do not** match tag strings 1:1. The planner already maps them via `_resolve_open_requirement()` / `load_category_course_index()` in `planning_agent.py`. Reuse that mapping for an optional **“Only show courses for my open requirements”** toggle when a transcript *is* uploaded — **not required for v1**.

### 2.3 Repo file location

Canonical path (gitignored locally; required in prod):

`project/course_planner/SCU_Find_Course_Sections.xlsx`

Copy the user’s `SCU_Find_Course_Sections.xlsx` there for dev/testing. After replacing the file, call `POST /api/courses/refresh` (already exists).

---

## 3. Current codebase (reuse, don’t rewrite)

| Piece | Location | Notes |
|-------|----------|--------|
| Schedule parser | `utils/scu_course_schedule_xlsx.py` | `_parse_days`, `_parse_time_range`, `_parse_course_tag_codes`, `load_all_course_sections`, `load_category_course_index`, `list_offered_courses` |
| Catalog API | `api/routers/courses.py` | `GET /api/courses` — deduped by course, **no tags**, one “representative” meeting time |
| Manual add UI | `web/src/components/AddCoursePicker.tsx` | Search-only dropdown; fetches catalog once |
| Add handler | `web/src/App.tsx` → `handleAddCourses` | Appends to `localOverride`; **not gated** on `fileUploaded` |
| Lab pairing | `list_offered_courses` → `lab_partner`; `AddCoursePicker` auto-adds lab | **R1** — keep behavior |
| Category index tests | `tests/test_category_index.py` | Proves Course Tags column parses |
| Slot click (R6) | `App.tsx` → `handleSlotClick` + `SlotSuggestionPopover` | Uses `POST /api/plan/suggest_for_slot`; **90-minute** query window today (`endMin = startMin + 90`) |
| New Plan | `App.tsx` → `handleNewPlan` | Clears plan; focuses chat; **no** manual vs AI chooser yet |
| Calendar grid | `CalendarView.tsx` | **30-minute** rows (`SLOT_MINUTES = 30`); click passes `slotIndex` |

**Gaps to close:**

1. API returns **course-level** rows, not **section-level** rows (Workday shows every section).
2. API omits **`course_tags`**, **`section`**, **`status`**, **`location`**.
3. No server-side **filter/query** — client would download ~1.6k sections if we expose all rows.
4. UI has no browse/filter layout.
5. **New Plan** and **calendar click** go straight to one path (chat / AI popover) with no “manual vs AI” choice.
6. Slot search window (90 min) does not match the **30-minute cell** the user clicked; overlap semantics need to be explicit and shared between catalog browse + AI suggest.

---

## 4. Product requirements

### 4.1 Must have (v1)

- [ ] **Works with zero transcript** — browser and add-to-plan never require `fileUploaded`.
- [ ] **Entry point:** Replace or augment `+ Add course` with **“Browse courses”** opening a modal/side panel (Workday-like).
- [ ] **Search:** Free text on course code, title, instructor (case-insensitive).
- [ ] **Filters (left panel):**
  - **Course subject** — multi-select from distinct `Course Subject` values.
  - **Meeting days** — Mon–Fri checkboxes (match if section meets on **any** selected day).
  - **Meeting times** — preset buckets, e.g. Morning (before 12), Afternoon (12–5), Evening (after 5); match if section **overlaps** bucket.
  - **Requirement / course tags** — multi-select from Core-relevant short codes (group under “Core” vs “Major/Pathways” in UI); match if section’s parsed tags include selection (OR within group).
- [ ] **Results table (main area):** Columns similar to Workday screenshot: Section, Subject, Number, Status, Instructors, Units, Meeting pattern, Location, Tags (truncated). Cap visible rows (e.g. 100) with “showing X of Y”.
- [ ] **Add action:** Row button **“Add to plan”** → calls existing `handleAddCourses` shape; auto-include **lab co-requisite** (R1).
- [ ] **Section choice:** When multiple sections exist for same `CSEN 174`, user picks **one section** (specific meeting time/instructor), not a merged row.
- [ ] **Duplicate guard:** Disable add if that **course code** is already on the calendar (same as today).
- [ ] **Empty states:** No xlsx on server → clear error. No matches → “Try clearing filters”.

### 4.2 Should have (v1.1)

- [ ] If transcript uploaded: optional filter **“Fits my open requirements”** using `missing_details` + `load_category_course_index` mapping.
- [ ] Show **★** on rows that satisfy **2+** open requirements (R2 alignment).
- [ ] Instructor rating chip when `instructor_ratings.csv` has data (R5 partial).

### 4.3 Explicitly out of scope

- Workday sync / browser automation (scripts stay in repo for teammate; **not** wired to UI).
- Filters: Instructional Format, Delivery Mode, Saved Searches, academic period picker (single term per xlsx file).
- PDF transcript upload.
- Replacing AI planner — manual path is parallel.

### 4.4 UX reference

User provided Workday screenshot: search bar on top, filters left, wide results table. **Ignore** irrelevant Workday filters (enrollment rules, etc.). Match SCU visual language (`--scu-red`, existing calendar/panel styles). Consider reading `.cursor/skills/frontend-design/SKILL.md` for polish.

### 4.5 New Plan — manual vs AI (must have)

When the user clicks **New Plan** in the left panel (`LeftPanel` → `onNewPlan` → `handleNewPlan`):

- [x] **Stop** jumping straight to “describe your preferences in chat” as the only path.
- [x] Show a **PlanStartModal** (or inline chooser) with two clear options:

| Option | Label (suggested) | Behavior |
|--------|-----------------|----------|
| **Manual** | “Search and add courses myself” | Reset plan state (same as today), open **Course Browser** with no filters, switch to **This Quarter** tab. Transcript **not** required. |
| **AI** | “Have AI recommend my schedule” | Reset plan state, focus chat, show short prompt: upload Academic Progress if missing, then describe preferences. Existing `ChatPanel` / `generatePlan` flow. |

- [x] Preserve RT#4 behavior: **do not** clear `fileUploaded`, `missingDetails`, or `parsedRows` on New Plan (only the active quarter plan + chat for that session).
- [ ] Optional third link: “Continue previous session” if `planSnapshots` exist — out of scope unless easy.

**Copy note:** Update `NEW_PLAN_TEXT` in `App.tsx` — it currently assumes AI-only (“describe your preferences…”).

### 4.6 Calendar click — time-scoped browse vs AI (must have)

When the user clicks an **empty** calendar cell (`CalendarView` → `onSlotClick`):

- [x] Show a **SlotActionModal** (small popover at click coordinates, similar to R6 placement) with two options:

| Option | Label (suggested) | Behavior |
|--------|-----------------|----------|
| **Browse** | “Search courses in this time” | Open **Course Browser** pre-filtered to clicked **day** + **time overlap** (see §5.6). |
| **AI suggest** | “AI suggestions for this slot” | Existing `SlotSuggestionPopover` / `suggest_for_slot` (requirement-ranked when transcript present). |

- [x] Do **not** auto-open AI popover without choice (replaces current behavior in `App.tsx` that sets `slotPopoverOpen` immediately).

**Overlap rule (core fix):** A section is included if its meeting on that weekday **intersects** the clicked time range:

```
section overlaps slot  ⇔  day_index ∈ meeting_days
                      AND meeting_start_min < slot_end_min
                      AND meeting_end_min > slot_start_min
```

This is the same interval test as `_slot_fits()` in `planning_agent.suggest_courses_for_slot` — **reuse one shared helper** in `scu_course_schedule_xlsx.py` (e.g. `section_overlaps_slot(...)`) for catalog API, AI suggest, and tests.

**Clicked slot dimensions (v1):**

| Setting | Value | Notes |
|---------|-------|-------|
| Grid cell size | **30 minutes** (keep `SLOT_MINUTES = 30` for now) | Matches current UI |
| Query range for click | **`[slotIndex * 30, slotIndex * 30 + 30)`** | User’s ask: anything meeting *during* that half-hour |
| Remove | `endMin = startMin + 90` in `handleSlotClick` | That widens search beyond the cell users clicked |

**Future options (document, do not block v1):**

- **1-hour cells:** `SLOT_MINUTES = 60` — fewer rows, coarser clicks.
- **Click day header only:** filter by weekday, no time constraint (browse all Monday classes).
- Config flag `CALENDAR_SLOT_MINUTES` shared by `CalendarView`, `App`, and API.

**“Anchored to slot” tag when adding from calendar:**

When the user adds a course from **Browse** (or AI suggest) opened via a calendar click:

- [x] Store metadata on the plan row, e.g. `_slotAnchored: true`, `_anchoredDayIndex`, `_anchoredStartMin`, `_anchoredEndMin`.
- [x] Show a small badge on the calendar block: **“Added for this time slot”** (or “Time set from slot pick”) so users know the block reflects their click, not necessarily the section’s real catalog time.
- [x] **Default display behavior (v1 product decision):** Render the course block at the **clicked slot’s start/end** for visual alignment, but show the **real** meeting time in the block subtitle (from catalog). Example: click 10:00–10:30 → block drawn there; subtitle `Actual: 9:15–10:20 AM`.
- [ ] **Alternative (stricter):** Use real catalog times for block position; badge only explains why it appeared in search. **Prefer subtitle + anchored draw** unless usability testing says otherwise.

When adding the **same** course from global Browse (not from a slot), do **not** set anchored metadata — use real `meeting_*` from the section row.

### 4.7 Integration matrix

| Entry point | Manual path | AI path | Transcript required? |
|-------------|-------------|---------|----------------------|
| New Plan → Manual | Course Browser (open) | — | No |
| New Plan → AI | — | Chat → `generatePlan` | Yes (existing gate) |
| Calendar → Browse | Course Browser (day + time prefilled) | — | No |
| Calendar → AI suggest | — | `SlotSuggestionPopover` | No for generic; better with transcript |
| Header “Browse courses” | Course Browser (no preset) | — | No |
| Chat | — | `generatePlan` | Yes |

---

## 5. Technical design

### 5.1 Backend — new catalog shape

Add function in `scu_course_schedule_xlsx.py`:

```python
def list_offered_sections(path: Path | None = None) -> list[dict[str, Any]]:
    """
    One dict per xlsx row (section), including:
      course_section, course, section, subject, number,
      title, units, status, enrolled_capacity,
      instructors[], meeting_days[], meeting_start_min, meeting_end_min,
      location, course_tags[]  # parsed short codes from _parse_course_tag_codes
      lab_partner  # same logic as list_offered_courses
    """
```

Implementation: single pass over xlsx (same loop as `load_all_course_sections` + read extra columns). Reuse `_parse_section_subject_number_with_sec`, `_parse_course_tag_codes`, title/units indexes.

Add **facet metadata** helper:

```python
def catalog_facets(sections: list[dict]) -> dict:
    # subjects: sorted unique
    # tag_groups: { "Core": ["RTC 1", ...], "Other": [...] }
    # time_buckets: constants
```

### 5.2 Backend — API

**Option A (recommended):** Extend `GET /api/courses`

Query params (all optional):

| Param | Example | Behavior |
|-------|---------|----------|
| `q` | `csen 174` | Substring match code/title/instructor |
| `subject` | `Computer Science and Engineering` | Repeatable or comma-separated |
| `days` | `0,2,4` | Weekday indices (Mon=0) |
| `time_bucket` | `morning,afternoon` | Overlap test (browse filters) |
| `day_index` | `2` | Single weekday (calendar click) |
| `start_min` | `120` | Minutes from calendar start (8 AM); **overlap** filter |
| `end_min` | `150` | Pair with `start_min` for slot overlap (§5.6) |
| `tag` | `RTC 3,ELSJ` | Section has any listed tag (normalized) |
| `limit` | `100` | Default 100, max 500 |
| `offset` | `0` | Pagination |

Response:

```json
{
  "sections": [ ... ],
  "total": 1635,
  "facets": { "subjects": [...], "tags": { "Core": [...] } },
  "count": 100
}
```

Keep existing `GET /api/courses` **without params** returning legacy `{ courses, count }` for backward compatibility OR version as `GET /api/courses/sections` to avoid breaking `AddCoursePicker` during migration.

**Option B:** New router `GET /api/catalog/sections` — cleaner separation.

Cache: `@lru_cache` on full section list; filters applied in Python in memory (≤2k rows is fine). Clear via existing `POST /api/courses/refresh`.

### 5.3 Tag matching rules

- Store tags on each section as **list of short codes** from `_parse_course_tag_codes`.
- Filter `tag=RTC 3` matches if `rtc 3` in normalized set (case-insensitive).
- Also match long descriptions if needed for academic-progress bridge (index keys already include both).
- **C&I 2:** Include if present in data; build facet list from actual file, not assumptions.

### 5.4 Frontend

**New files:**

- `web/src/components/CourseBrowser.tsx` — modal/panel layout
- `web/src/components/CourseBrowserFilters.tsx` — left filter column
- `web/src/components/CourseBrowserTable.tsx` — results table
- `web/src/hooks/useCourseCatalog.ts` — debounced fetch with query params

**Update:**

- `web/src/api/client.ts` — `searchCatalogSections(params)`, types `CatalogSection`, `CatalogFacets`
- `web/src/App.tsx` — wire **Browse courses** button; pass `onAdd` → `handleAddCourses`
- Deprecate or embed `AddCoursePicker` (keep quick search inside browser header)

**Add flow mapping** (`CatalogSection` → plan row):

```typescript
{
  course: "CSEN 174",           // subject + number (not section suffix)
  title, units,
  best_professor: instructors[0],
  meeting_days, meeting_start_min, meeting_end_min,
  category: "Manually added",
  reason: "Added manually",
  _manualAdd: true,
  _section: 1,                  // optional metadata for future section switcher
}
```

If user adds `CSEN 174-1` meeting MW 8am, store **that section’s** meeting fields (from row), not a different section’s.

**Lab:** If row has `lab_partner` and partner not in plan, append partner with **its** default section from catalog (same as `AddCoursePicker` today).

### 5.5 Shared slot overlap helper

Add to `scu_course_schedule_xlsx.py`:

```python
def section_overlaps_slot(
    section: dict[str, Any],
    *,
    day_index: int,
    start_min: int,
    end_min: int,
) -> bool:
    """True if section meets on day_index and [meeting_start, meeting_end) overlaps [start_min, end_min)."""
```

Use in:

- `list_offered_sections` filtering (`GET /api/catalog/sections?day_index=&start_min=&end_min=`)
- `suggest_courses_for_slot` — replace inline `_slot_fits` body with this helper; pass **30-minute** window from frontend
- Unit tests in `tests/test_catalog_sections.py` and extend `tests/test_r6_slot_suggestion.py`

**Example:** Class meets 8:00–9:05 AM (offsets 0–65). User clicks 9:00–9:30 cell (offsets 60–90). Overlap exists (65 > 60). **Must appear** in browse + suggest lists.

### 5.6 Frontend — modals and Course Browser context

**New components:**

- `PlanStartModal.tsx` — New Plan chooser (manual / AI)
- `SlotActionModal.tsx` — Calendar click chooser (browse / AI)
- Extend `CourseBrowser.tsx` with optional `initialFilters`:

```typescript
type CourseBrowserLaunchContext =
  | { mode: "open" }
  | { mode: "slot"; dayIndex: number; startMin: number; endMin: number; label: string };
```

When launched from a slot, show a read-only banner:  
`Showing courses that meet Wednesday 10:00–10:30 AM (any overlap)` with “Clear time filter”.

**App state additions:**

```typescript
const [courseBrowserOpen, setCourseBrowserOpen] = useState(false);
const [courseBrowserContext, setCourseBrowserContext] = useState<CourseBrowserLaunchContext>({ mode: "open" });
const [planStartModalOpen, setPlanStartModalOpen] = useState(false);
```

**`handleNewPlan` change:**

```typescript
// Instead of immediately setMessages(NEW_PLAN_TEXT):
setPlanStartModalOpen(true);
// On Manual: reset plan fields, setCourseBrowserContext({ mode: "open" }), setCourseBrowserOpen(true)
// On AI: reset plan fields, setMessages(AI_NEW_PLAN_TEXT), setChatFocusNonce(...)
```

**`handleSlotClick` change:**

```typescript
const startMin = slotIndex * 30;
const endMin = startMin + 30;  // NOT +90
setSlotActionData({ dayIndex, slotIndex, startMin, endMin, clientX, clientY });
setSlotActionModalOpen(true);
// Browse → open CourseBrowser with slot context
// AI → open SlotSuggestionPopover with same startMin/endMin
```

Wire `SlotSuggestionPopover` / `suggestCoursesForSlot` to use the **30-minute** window.

### 5.7 Calendar block rendering (anchored courses)

Update `recommendedToCalendarBlocks` (`web/src/utils/planCalendar.ts`):

- If `_slotAnchored` and anchored offsets present, use anchored offsets for `startOffsetMin` / `endOffsetMin`.
- Pass through `actualMeetingLabel` from real `meeting_start_min` / `meeting_end_min` for display in `CalendarView` course blocks.

### 5.8 Transcript independence

| Feature | Requires transcript? |
|---------|---------------------|
| Open Course Browser | **No** |
| Add to calendar | **No** |
| AI chat planning | **Yes** (existing gate in `ChatPanel.sendText`) |
| Slot popover suggestions | Works with empty `missing_details` (general courses) |
| “Fits my open requirements” filter | **Yes** (v1.1) |
| New Plan → Manual | **No** |
| Calendar → Browse | **No** |

No change needed to `fileUploaded` for manual add — verify in test.

---

## 6. Implementation phases (agent checklist)

### Phase 0 — Setup

- [x] Copy `SCU_Find_Course_Sections.xlsx` into `project/course_planner/` (if missing).
- [x] Run `pytest tests/test_category_index.py` — confirms tags parse.
- [x] Read `AGENTS.md` R1 (lab pairing).

### Phase 1 — Backend (TDD)

- [x] Add `tests/test_catalog_sections.py`:
  - Parses sample row tags (`RTC 3`, `ELSJ`, `C&I 1`)
  - `list_offered_sections` returns multiple sections per course
  - Filter by subject + tag + day
- [x] Implement `list_offered_sections` + `catalog_facets`
- [x] Add API endpoint with query params
- [x] Extend `POST /api/courses/refresh` to clear new caches

### Phase 2 — Frontend core

- [x] API client + types
- [x] `CourseBrowser` modal with search + table
- [x] Wire to `App.tsx` (visible in **This Quarter** tab)
- [ ] Manual test: add course without upload → appears on calendar
- [x] `PlanStartModal` + update `handleNewPlan` (manual opens browser, AI focuses chat)
- [x] `SlotActionModal` + update `handleSlotClick` (30-min window, chooser before popover/browser)

### Phase 3 — Filters

- [x] Subject multi-select
- [x] Day checkboxes
- [x] Time bucket checkboxes
- [x] Tag multi-select (grouped); debounce API calls 300ms
- [x] Course Browser: apply `initialFilters` from slot context (`day_index`, `start_min`, `end_min`)
- [x] Fix `suggest_courses_for_slot` / `handleSlotClick` to use shared overlap + 30-min slot (remove +90)

### Phase 4 — Polish & tests

- [ ] Vitest: browser opens without `fileUploaded`; add calls `handleAddCourses`
- [x] Vitest: New Plan shows chooser; Manual opens browser; AI focuses chat
- [ ] Vitest: calendar click shows chooser; Browse passes day/time filters
- [x] Pytest: overlap includes class that starts before slot but ends during slot
- [x] Anchored badge + calendar draw at clicked slot; subtitle shows actual time
- [ ] Accessibility: keyboard nav, `aria-label` on filters, focus trap in modal
- [ ] Mobile: filters collapse to drawer
- [ ] Update `HANDOFF.md` file map

### Phase 5 — Optional v1.1

- [ ] “My open requirements” filter when `missing_details` present
- [ ] Double-tag ★ indicator
- [ ] Calendar: 1-hour cells and/or “click day column header” browse mode

---

## 7. Test plan (human QA)

1. **No transcript:** Open app → Browse courses → filter `RTC 3` → add a course → shows on calendar.
2. **Search:** Query `chinese` or `CHIN` → relevant courses appear.
3. **Days:** Select Tuesday/Thursday only → only T Th sections.
4. **Lab pair:** Add `CSEN 194` → `CSEN 194L` auto-added (if offered).
5. **Duplicate:** Add same course twice → second blocked/disabled.
6. **With transcript:** Upload xlsx → optional “open requirements” filter narrows list.
7. **Deploy:** Confirm `SCU_Find_Course_Sections.xlsx` on server and `/api` reachable.
8. **New Plan → Manual:** No transcript → browser opens → add course → on calendar.
9. **New Plan → AI:** Without transcript → chat asks for upload; with transcript → planning works.
10. **Calendar overlap:** Click 10:00–10:30 → Browse → a 9:15–10:20 class appears; add → badge “Added for this time slot” + subtitle shows real time.
11. **Calendar AI:** Same slot → AI suggest → still works; uses same 30-min overlap window.
12. **RT#4 regression:** New Plan still preserves uploaded transcript.

---

## 8. Risks & decisions

| Risk | Mitigation |
|------|------------|
| Large payload if returning all sections unfiltered | Server-side filter + pagination; default `limit=100` |
| Tag spelling mismatch (transcript vs xlsx) | Reuse `load_category_course_index` keys; don’t invent new mapping |
| COEN/CSEN duplicate rows | Collapse display: prefer CSEN label; keep alias keys in index |
| Multiple sections, one calendar block per course | Store chosen section’s meeting times; future: “change section” |
| xlsx missing in prod | API 503 with message; UI banner |
| Anchored draw vs real time confuses users | Subtitle always shows actual catalog time; tooltip explains anchor |
| 30-min cells feel cramped | v1.1: 60-min grid or day-level click |

**Decision for agent:** Prefer **`GET /api/catalog/sections`** as new endpoint to avoid breaking existing `listCourses()` consumers; frontend migrates `AddCoursePicker` to thin wrapper over browser or deprecates dropdown.

---

## 9. Files to touch (summary)

```
project/course_planner/utils/scu_course_schedule_xlsx.py   # list_offered_sections, facets
project/api/routers/courses.py                           # or new catalog.py router
project/tests/test_catalog_sections.py                   # new
project/web/src/api/client.ts
project/web/src/components/CourseBrowser*.tsx              # new
project/web/src/components/PlanStartModal.tsx              # new
project/web/src/components/SlotActionModal.tsx               # new
project/web/src/utils/planCalendar.ts                        # anchored block rendering
project/web/src/components/CalendarView.tsx                  # anchored badge in blocks
project/web/src/App.tsx
project/web/src/components/LeftPanel.tsx                     # New Plan still calls onNewPlan
project/course_planner/agents/planning_agent.py              # suggest_courses_for_slot → shared overlap
project/tests/test_r6_slot_suggestion.py                     # 30-min overlap cases
project/tests/app/course-browser.test.tsx                  # new Vitest
project/tests/app/new-plan-reset.test.tsx                    # extend for chooser + RT#4
HANDOFF.md                                                 # doc update
```

**Do not modify:** Workday automation scripts, `ChatPanel` transcript gate for AI (except copy tweaks for AI path). Refactor `planning_agent.suggest_courses_for_slot` only to use shared overlap helper.

---

## 10. Answer to product question: “Do course sections have requirements?”

**Yes.** The `Course Tags` column in `SCU_Find_Course_Sections.xlsx` lists requirements each section fulfills (ELSJ, RTC 1–3, C&I, etc.). The repo already parses this column for AI planning. **No xlsx change required** for requirement filtering unless tags are missing for specific courses — if so, re-export from Workday with Course Tags visible or ask admin to refresh the catalog file.

If a course has **empty** tags in the xlsx, it will only appear in unfiltered browse/search, not under requirement filters — document this in UI helper text.
