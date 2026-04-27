# SCU Course Planner - C4 Architecture

This document contains the C4 diagrams for the consolidated product as the team moves from separate prototypes to one shared codebase.

## Consolidation Direction and Rationale

- **Foundation:** Start from Ismael's prototype because it currently has the strongest UI baseline.
- **Keep from Jason:** Wizard-style guided input flow, but reduce heavy free-response to one focused free-text section.
- **Keep from Ismael:** Next-quarter planning UI patterns and calendar integration.
- **Keep from Joey:** Four-year plan integration and persistence so students can return later.
- **Keep from Jiasheng:** Major requirement website URL ingestion/fetching to enrich planning context.
- **Leave behind:** Prototype-specific UIs that were confusing or too dense, and workflows that require excessive typing.

## Design Iteration Notes (AI-assisted)

- We rejected "frontend calls Gemini directly" because it would expose API keys and weaken controls.
- We chose a Python backend service boundary for AI orchestration so prompts, model settings, and safety checks are centralized.
- We discussed storing full transcript documents, but decided to store only derived requirement status and planning artifacts where possible to reduce privacy risk.
- We selected SQLite for the consolidated phase to keep setup simple while the team converges on one codebase.
- We kept clear container boundaries so each owner has a distinct implementation area and fewer merge conflicts.

## C4 Context Diagram

```mermaid
C4Context
    title SCU Course Planner - System Context (Consolidated Product)

    Person(student, "SCU Undergraduate Student", "Plans next quarter, tracks long-term plan, and checks requirement progress")
    Person(advisor, "Academic Advisor (optional)", "Reviews student plan during advising conversations")

    System(coursePlanner, "SCU Course Planner", "Web app for next-quarter planning + four-year plan support with AI-assisted recommendations")

    System_Ext(gemini, "Google Gemini API", "Generates schedule recommendations and reasoning")
    System_Ext(majorWeb, "Major Requirement Website URL", "Program requirements found on Undergraduate Bulletin")
    System_Ext(scuData, "SCU Course Data Sources", "Workday, SCU Course Evals used for schedule generation")

    Rel(student, coursePlanner, "Uses course planning features", "HTTPS")
    Rel(advisor, coursePlanner, "Reviews saved student planning output", "HTTPS")
    Rel(coursePlanner, gemini, "Sends planning context, receives recommendations", "HTTPS/JSON")
    Rel(coursePlanner, majorWeb, "Fetches major requirements", "HTTP/HTTPS")
    Rel(coursePlanner, scuData, "Reads course and section information", "API/ingest")
```

## C4 Container Diagram

```mermaid
C4Container
    title SCU Course Planner - Container View (Consolidated Product)

    Person(student, "SCU Undergraduate Student", "Uses browser-based planner")

    System_Boundary(sp, "SCU Course Planner") {
        Container(frontend, "Web Front End", "React + TypeScript + Vite", "Wizard input flow, calendar UI, four-year plan pages, and recommendation display")
        Container(backend, "Backend API", "Python (FastAPI)", "API endpoints, validation, auth/session logic, planning orchestration, and data APIs")
        Container(aiLayer, "AI Integration Layer", "Python service/module", "Builds prompts, calls Gemini, parses responses, and applies guardrails")
        Container(ingest, "Requirements/Course Ingestion", "Python jobs/services", "Fetches major requirement URL data and normalizes course metadata")
        ContainerDb(db, "Application Database", "SQLite", "User account data, fulfilled/missing requirements, saved plans, and recommendation history")
    }

    System_Ext(geminiApi, "Google Gemini API", "LLM inference")
    System_Ext(majorReqUrl, "SCU Undergradaute Bulletin", "Major requirements source")
    System_Ext(courseFeeds, "SCU Course Data Sources", "CCurse catalog/section feed")

    Rel(student, frontend, "Uses", "HTTPS")
    Rel(frontend, backend, "Calls REST API", "HTTPS/JSON")
    Rel(backend, aiLayer, "Requests recommendation generation", "Internal call")
    Rel(aiLayer, geminiApi, "Sends prompts and receives model output", "HTTPS/JSON")
    Rel(backend, ingest, "Triggers/schedules data refresh", "Internal call")
    Rel(ingest, majorReqUrl, "Fetches requirement information", "HTTP/HTTPS")
    Rel(ingest, courseFeeds, "Fetches catalog/section information", "API/ETL")
    Rel(backend, db, "Reads/writes app data", "SQL")
```

## Ownership Mapping to Containers

- **Ismael (Front End):** `Web Front End`
- **Joey (Database + Backend integration):** `Application Database` and backend-to-database integration paths
- **Jiasheng (Backend security/accounts):** backend account/auth/session components in `Backend API`
- **Jason (AI + remaining backend):** `AI Integration Layer` and remaining backend orchestration in `Backend API`



