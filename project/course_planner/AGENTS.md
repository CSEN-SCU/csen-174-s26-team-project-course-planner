# AGENTS.md — SCU Course Planner

## Run application
```bash
cd project/course_planner
streamlit run main.py
```

## Run tests
```bash
cd project/course_planner
python -m pytest tests/
```

## Install dependencies
```bash
cd project/course_planner
pip install -r requirements.txt
```
Voice transcription uses the `SpeechRecognition` package and **Google’s speech API over the network** when you click **Transcribe recording → preferences**.

## Key environment variables
- `GEMINI_API_KEY` or `GOOGLE_API_KEY` — required for planning agent, curriculum PDF gap analysis, and embeddings
- `GEMINI_MODEL` — optional, defaults to `gemini-2.5-flash`
- `SCU_PLANNER_COOKIE_KEY` — auth cookie signing key
- `COURSE_PLANNER_DB` — optional path to SQLite DB

## Project layout
- `.streamlit/config.toml` — Streamlit theme (SCU primary red `#C8102E`, light surfaces)
- `utils/scu_theme.py` — extra CSS for headings, sidebar strip, link accents (`#8B0000` dark red)
- `main.py` — Streamlit entry point, all UI logic (Step 3 calendar **Remove & replace from gaps** → `plan_for_user` + `utils/calendar_plan_followup.py`)
- `agents/` — planning, professor, memory, orchestrator agents
- `auth/` — login/register via streamlit-authenticator
- `db/` — SQLite connection, schema, migrations
- `utils/` — xlsx parsers, helpers
- `specs/` — Ralph specs (source of truth for behavior)
- `data/` — local SQLite DB (gitignored)

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