# SCU Course Planner (`course_planner`)

Python + Streamlit prototype for parsing SCU **View My Academic Progress** exports (`.xlsx`) locally. Optional Gemini-based agents (e.g. PDF requirement sheets) live under `agents/`.

---

## Target architecture (multi-agent pipeline)

**User input:** major + completed courses + preferences

↓

```
┌─────────────────────────────┐
│     Orchestrator Agent      │  ← decomposes tasks
└─────────────────────────────┘
```

↓

### PHASE 1 — Information gathering (linear)

**Requirement Agent**

- Accepts a URL from the user.
- **Web fetch** of the official major-requirements page (or linked documents).
- Parses **PDF / images** using a **vision-capable LLM** (multimodal) when needed.
- **Output:** which required courses are still missing (the “gap” vs. the major sheet).

↓

### PHASE 2 — Planning (chatbot)

**Planning Chatbot Agent**

- Combines the **requirement gap** with **user preferences** (time slots, difficulty, interests).
- **Searches** next-term course offerings / sections.
- Calls **Professor Agent** to score and rank sections.
- **Output:** a recommended schedule plan.

↓ **(parallel where applicable)**

| Professor Agent | Schedule Agent |
|-----------------|----------------|
| RateMyProfessor / SCU course eval signals | Detect **time conflicts** |
| Rank instructors per section | Improve **time distribution** across the week |

↓

### PHASE 3 — Presentation + execution

**Frontend**

- **Left:** calendar-style weekly grid (Google Calendar–like).
- **Right:** ranked recommended course list (professor signals, difficulty, meeting times).

After the user selects courses → *(optional)*

**Email Agent**

- Drafts outreach email: *“Professor X, I am interested in joining COEN 146 …”*
- **Human-in-the-loop:** user reviews and confirms before anything is sent.

---

## Current implementation (this folder)

| Component | Status |
|-----------|--------|
| Streamlit UI + SCU Academic Progress `.xlsx` parser | Implemented (`main.py`, `utils/academic_progress_xlsx.py`) |
| Gemini `requirement_agent` (PDF + completed list) | Stub / experimental (`agents/requirement_agent.py`) |
| Orchestrator, Planning Chatbot, Professor, Schedule, Email agents | Not implemented yet |

### Run locally

```bash
cd course_planner
pip install -r requirements.txt
# Optional for Gemini features: set GEMINI_API_KEY or GOOGLE_API_KEY in .env (see .env.example)
streamlit run main.py
```

Secrets: copy `.env.example` to `.env`. Do **not** commit `.env`.
