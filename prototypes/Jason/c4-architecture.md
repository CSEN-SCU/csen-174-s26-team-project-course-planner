# Jason Prototype - C4 Architecture

This document describes the architecture for Jason's prototype only (guided wizard planner).

## Design Focus

- Prioritized a guided wizard flow to collect student context and constraints before recommendation generation.
- Kept backend and persistence lightweight (`Express` + `NeDB`) to move quickly for prototype validation.
- Integrated Gemini through the backend (not the browser) so API keys remain server-side.
- Included fallback seeded schedules when Gemini is not configured, so the demo is still usable.

## C4 Context Diagram

```mermaid
C4Context
    title Jason Prototype - System Context

    Person(student, "SCU Undergraduate Student", "Completes wizard and reviews schedule options")
    Person(advisor, "Academic Advisor (optional)", "Reviews generated schedules with student")

    System(jasonPrototype, "Jason Guided Wizard Prototype", "Web-based planning wizard that generates and saves schedule options")

    System_Ext(geminiApi, "Google Gemini API", "Generates explainable schedule recommendations")

    Rel(student, jasonPrototype, "Uses to input preferences and generate schedules", "HTTPS")
    Rel(advisor, jasonPrototype, "Views schedule options during advising", "HTTPS")
    Rel(jasonPrototype, geminiApi, "Sends prompt context and receives recommendations", "HTTPS/JSON")
```

## C4 Container Diagram

```mermaid
C4Container
    title Jason Prototype - Container View

    Person(student, "SCU Undergraduate Student", "Uses planner in browser")

    System_Boundary(jp, "Jason Guided Wizard Prototype") {
        Container(frontend, "Wizard Front End", "HTML + CSS + JavaScript", "Collects user inputs and displays generated schedule options")
        Container(api, "Prototype Backend API", "Node.js + Express", "Serves UI, validates inputs, orchestrates recommendation generation, and exposes plan endpoints")
        Container(aiModule, "AI Recommendation Module", "Server-side module (`@google/generative-ai`)", "Builds prompts, calls Gemini, and parses model output")
        ContainerDb(planDb, "Plan Store", "NeDB (`data/plans.db`)", "Stores generated plans and retrieval history")
    }

    System_Ext(gemini, "Google Gemini API", "LLM inference")

    Rel(student, frontend, "Uses", "HTTPS")
    Rel(frontend, api, "Calls API endpoints", "HTTPS/JSON")
    Rel(api, aiModule, "Requests recommendation generation", "Internal call")
    Rel(aiModule, gemini, "Sends prompts and receives completions", "HTTPS/JSON")
    Rel(api, planDb, "Reads/writes generated plans", "NeDB operations")
    Rel(frontend, planDb, "No direct access", "N/A")
```
