[![Review Assignment Due Date](https://classroom.github.com/assets/deadline-readme-button-22041afd0340ce965d47ae6ef1cefeee28c7c493a6346c4f15d667ab976d596c.svg)](https://classroom.github.com/a/NfqHRKdw)

# SCU Course Planner (CSEN 174)

## Team name

Update with your official classroom team name.

## Product name

**SCU Course Planner**

## One-sentence description

An LLM-powered web app that helps SCU undergraduates plan next-quarter schedules using transcript context and course quality/workload signals, with less friction than Workday-only planning.

## Team members

- Jason
- Ismael
- Joey
- Jiasheng

## Target architecture (multi-agent pipeline)

Product direction: students provide **major**, **completed courses**, and **preferences**; an **Orchestrator** routes work through phased agents.

1. **PHASE 1 — Information gathering (linear)**  
   **Requirement Agent:** user-supplied **URL** → web fetch of major-requirements content → parse **PDF / images** with a **vision-capable LLM** when needed → output **missing required courses** (gap analysis).

2. **PHASE 2 — Planning (chatbot)**  
   **Planning Chatbot Agent:** merges requirement **gap** + **preferences** (time / difficulty / interests) → searches **next-term offerings** → invokes **Professor Agent** for scoring/ranking → proposes a **recommended schedule**.

   In parallel (where applicable):  
   - **Professor Agent:** RateMyProfessor / SCU evaluation signals → rank instructors.  
   - **Schedule Agent:** **time conflicts** + **time distribution** optimization.

3. **PHASE 3 — Presentation + execution**  
   **Frontend:** left pane — **calendar-style** week grid; right pane — **recommended course list** (professor signals, difficulty, times).  
   **Optional Email Agent:** drafts instructor email (*“Professor X, I am interested in joining COEN 146 …”*) with **human-in-the-loop** approval before send.

Implementation sketch and current `course_planner` scope: see [`project/course_planner/README.md`](project/course_planner/README.md).

## Repository layout

| Path | Purpose |
|------|---------|
| [`product-vision.md`](product-vision.md) | Product vision (Moore template) + HMW + canvas insights |
| [`problem_framing_canvas.md`](problem_framing_canvas.md) | Full Problem Framing Canvas |
| [`architecture/architecture.md`](architecture/architecture.md) | C4 Context + Container diagrams (Mermaid) |
| [`.cursorrules`](.cursorrules) | Cursor / AI agent project context |
| [`project/course_planner/`](project/course_planner/) | Python + Streamlit app: Academic Progress `.xlsx` parsing; roadmap agents (see `project/course_planner/README.md`) |
| [`prototypes/`](prototypes/) | Each teammate’s divergent prototype |
| [`prototypes/Jason/`](prototypes/Jason/) | Jason’s guided-wizard prototype (see its `README.md`) |
| [`prototypes/jiasheng/`](prototypes/jiasheng/) | Jiasheng’s FastAPI prototype: Academic Progress upload + major requirements + course sections (see its `README.md`) |
| [`prototypes/joey/`](prototypes/joey/) | Joey's prototype: Long Term Advising/Four Year Planning (see its `README.md`) |
| [`prototypes/ismael/`](prototypes/ismael/) | Ismael's prototype: (see its `README.md`) |

## Secrets

Do not commit `.env` files. Use `prototypes/<name>/.env.example` as a template for local API keys.

