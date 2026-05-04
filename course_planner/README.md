# SCU Course Planner — `course_planner/`

Python + Streamlit prototype. Upload your SCU Academic Progress export and get a personalized next-quarter schedule with professor ratings and a weekly calendar view.

---

## Current implementation

| Step | Module | How |
|------|--------|-----|
| Requirement parsing | `main.py` → `parse_academic_progress_xlsx` | Parses SCU “View My Academic Progress” `.xlsx` export locally, extracts Not Satisfied courses |
| Schedule planning | `agents/planning_agent.py` | Gemini LLM — takes missing courses + user preference string, returns recommended schedule |
| Professor rating | `agents/professor_agent.py` | RateMyProfessor API (parallel threads) — enriches each recommended course with instructor rating, difficulty, would-take-again % |
| Calendar view | `main.py` | Streamlit `st.columns` grid — maps courses to Mon–Fri using SCU Find Course Sections `.xlsx` |

---

## Roadmap (not yet in UI)

| Agent | Status | Notes |
|-------|--------|-------|
| Requirement Agent (LLM) | Implemented, not wired | `agents/requirement_agent.py` — Gemini vision reads major requirement PDF, outputs gap analysis. Will replace/supplement Excel parsing. |
| Orchestrator | Placeholder | `agents/orchestrator.py` — will route tasks across agents |
| Email Agent | Planned | Draft add-permission email to professor, human-in-the-loop before send |

---

## Architecture

```
Academic Progress (.xlsx)
        ↓
Requirement Parser (local)          ← LLM version: agents/requirement_agent.py (roadmap)
        ↓
Planning Agent (Gemini)  ←  user preference (natural language)
        ↓
Professor Agent (RateMyProfessor API, parallel)
        ↓
Calendar UI (Streamlit)
```

---

## Run locally

```bash
cd course_planner
pip install -r requirements.txt
cp .env.example .env   # add your GOOGLE_API_KEY
streamlit run main.py
```

Do **not** commit `.env`; keep secrets out of version control.

---

## Required files

Place these in `course_planner/` (not committed — see `.gitignore`):

| File | Where to get it |
|------|-----------------|
| `View_My_Academic_Progress.xlsx` | SCU Workday → View My Academic Progress → Export |
| `SCU_Find_Course_Sections.xlsx` | SCU Workday → Find Course Sections → Export |

---

## Team

Jason · Ismael · Joey · Jiasheng
