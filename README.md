[![Review Assignment Due Date](https://classroom.github.com/assets/deadline-readme-button-22041afd0340ce965d47ae6ef1cefeee28c7c493a6346c4f15d667ab976d596c.svg)](https://classroom.github.com/a/NfqHRKdw)

# SCU Course Planner (CSEN 174)

## Team Name

SCU Course Planner


## Description

SCU Course Planner is a web app that helps SCU students plan their future schedules using transcript context and course quality/workload signals, with less friction than Workday-only planning.

This repo contains:

- **`project/course_planner/`** — Python + Streamlit prototype: Academic Progress parsing, Gemini-backed schedule recommendations, RateMyProfessor enrichment, **local accounts**, **per-user RAG memory** (SQLite + sqlite-vec), and chat-style follow-up replies. See [`project/course_planner/README.md`](project/course_planner/README.md).
- **`project/web/`** + **`project/api/`** — React + Express + Prisma prototype (`bronco-plan-api`) for eligible courses and schedule APIs.

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

Implementation sketch and **current Streamlit prototype** scope: [`project/course_planner/README.md`](project/course_planner/README.md).

## Repository layout

| Path | Purpose |
|------|---------|
| [`product-vision.md`](product-vision.md) | Product vision (Moore template) + HMW + canvas insights |
| [`problem_framing_canvas.md`](problem_framing_canvas.md) | Full Problem Framing Canvas |
| [`architecture/architecture.md`](architecture/architecture.md) | C4 Context + Container diagrams (Mermaid) |
| [`.cursorrules`](.cursorrules) | Cursor / AI agent project context |
| [`project/course_planner/`](project/course_planner/) | Python + Streamlit: accounts, RAG memory, planning orchestrator, agents (see its [`README.md`](project/course_planner/README.md)) |
| [`project/api/`](project/api/) | TypeScript Express API + Prisma (courses, transcript parse, schedule endpoints) |
| [`project/web/`](project/web/) | React + Vite frontend |
| [`prototypes/`](prototypes/) | Each teammate’s divergent prototype |
| [`prototypes/Jason/`](prototypes/Jason/) | Jason’s guided-wizard prototype (see its `README.md`) |
| [`prototypes/jiasheng/`](prototypes/jiasheng/) | Jiasheng’s FastAPI prototype (see its `README.md`) |
| [`prototypes/joey/`](prototypes/joey/) | Joey's prototype: Long Term Advising/Four Year Planning (see its `README.md`) |
| [`prototypes/ismael/`](prototypes/ismael/) | Ismael's prototype (see its `README.md`) |

## Secrets

Do not commit `.env` files. Use `project/course_planner/.env.example` or `prototypes/<name>/.env.example` as templates for local API keys.

Do not commit `project/course_planner/data/` — it holds the local SQLite database for accounts and memory (see `.gitignore`).
