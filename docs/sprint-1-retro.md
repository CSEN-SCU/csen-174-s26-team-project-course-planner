# Sprint 1 Retrospective (W6D2)

## What went well in Sprint 1?

In Sprint 1, we focused on building a sustainable development foundation first. We set up and expanded a testing baseline (unit + integration, with an end-to-end mindset for user-visible flows), and we actually used the **Red → Green** loop instead of treating tests as “documentation that nobody runs.” A concrete example: while running our tests, we identified a “contract gap” in backend security functionality and filled in missing session/password-related modules so that targeted tests moved from Red to Green and stayed reproducible.

Collaboration also improved because we aligned on module ownership first (based on `architecture/architecture.md`), then split test writing by that ownership, and labeled new test files by author. That reduced coordination overhead (“who owns this failure?”) and made failures easier to route and debug. Overall, tests became more predictable to run, bugs were easier to isolate, and we now have a stronger regression safety net going into feature work.

## What could be improved?

Sprint 1 delivered tests and baseline security modules, but from a “usable product that can evolve” perspective we still lack two key capabilities: a **user account system** and **per-user LLM memory / long-term context**. Right now the app feels closer to a single-user/single-session experience: we cannot reliably isolate preferences and planning data per user, and LLM context does not persist across repeated usage. That’s a major gap for course planning, where students iteratively revise plans over multiple days/weeks.

Our testing work also exposed areas to improve: (1) keep a cleaner boundary between tests and implementation details so tests remain stable under refactors, and (2) add more end-to-end validation of **user-level behaviors** (e.g., data isolation after login, memory never leaking across users, and correct behavior when sessions expire). In Sprint 2 we should extend tests from “engineering foundation” into “product behavior guarantees.”

## Celebrate (specific people + specific contributions)

Use this table during/after class for **Jiasheng, Jason, Ismael, and Joey** to fill in and confirm specific contributions. Aim to include concrete artifacts (files/modules/tests/bugs fixed/PRs) and the impact of the work.

| Member | Specific contributions (what you built, where it lives, and why it mattered) |
|---|---|
| **Jiasheng** | add rate my professor api to llm recommand system, add feature that pattern match user's transcript to fetch.  |
| **Jason** | Added AI-provider fallback behavior so schedule generation returns a safe fallback response when the upstream model is unavailable/rate-limited instead of timing out with a user-facing error; also added/maintained Jason-owned AI tests to validate provider selection and fallback behavior (`project/course_planner/tests/jason/test_planning_agent_provider_fallback.py`) and authored red tests for next API features (`project/course_planner/tests/jason/test_planning_agent_future_features_red.py`). |
| **Ismael** | (to fill in) |
| **Joey** | (to fill in) |

## AI tools reflection (two short paragraphs)

AI tools were most helpful for test work this sprint. Using Cursor/Claude, we could generate a lot of **correctly-structured** test scaffolding quickly (Arrange/Act/Assert), fill in repetitive boilerplate (setup, mocks, common assertions), and expand unit + integration coverage with less manual typing. In our case, AI was especially effective at translating “what behavior should users rely on?” into executable test descriptions, which we then refined into stronger assertions (for example: session cookie security flags, password storage properties like unique salts and verification behavior). Net effect: going from zero to a runnable test file was dramatically faster.

AI also made some things harder. First, without full context it can **invent APIs/paths** that look plausible but fail immediately when run, which forces extra time to reconcile real module boundaries and imports. Second, AI-generated assertions often drift toward implementation details (e.g., hard-coding a specific hash prefix or internal structure), which can make tests brittle during refactors unless we correct them. Third, when tests fail, AI suggestions can be overconfident and push changes in the wrong layer “just to make it green.” Our practical workflow this sprint was: let AI accelerate drafts and edge-case enumeration, but keep humans responsible for anchoring tests on user-observable behavior and enforcing the Red→Green minimal-change discipline.

## Sprint 2 commitments (2–3 improvements + linked Kanban cards)

In Sprint 2, we commit to extending our Sprint 1 testing foundation into “multi-user + durable memory” product capabilities. Each commitment maps directly to a Kanban card:

1) **Integrate the 4-Year Plan feature into the main workflow**  
   - Kanban card: [Issue #5 — Integrate 4 Year Plan Feature](https://github.com/CSEN-SCU/csen-174-s26-team-project-course-planner/issues/5)  
   - What we will do: define the 4-year plan data model and UI entry points; add tests for key flows (at minimum: create/edit and a primary “view/export” path) so existing behavior stays stable as we ship new functionality.

2) **Add a user account system (login/session/data isolation)**  
   - Kanban card: [Issue #6 — Add User Account System](https://github.com/CSEN-SCU/csen-174-s26-team-project-course-planner/issues/6)  
   - What we will do: implement a minimum viable account + session flow; define acceptance criteria for user data isolation; add end-to-end coverage (each user sees only their own data, correct behavior after logout/session expiration).

3) **Add a per-user RAG/memory database (LLM personalization over time)**  
   - Kanban card: [Issue #9 — add RAG database for user](https://github.com/CSEN-SCU/csen-174-s26-team-project-course-planner/issues/9)  
   - What we will do: bind memory storage/retrieval to a userId; implement a minimal retrieval chain (write → retrieve → inject into prompts/context); add tests and basic guardrails to prevent cross-user leakage (retrieve only current user memory, controllable top-k and context length limits).

4) **Add AI recommendation explainability fields and confidence rationale**  
   - Kanban card: *(https://github.com/CSEN-SCU/csen-174-s26-team-project-course-planner/issues/12)*  
   - What we will do: extend schedule API responses with short, user-readable explanation fields per recommended course (why it was selected, tradeoffs, and confidence rationale) so students can trust recommendations; add contract tests to ensure explanation fields are always present and non-empty.

5) **Add user feedback loop endpoint for recommendation quality tuning**  
   - Kanban card: *(https://github.com/CSEN-SCU/csen-174-s26-team-project-course-planner/issues/13)*  
   - What we will do: implement an endpoint for thumbs-up/down and swap reasons on recommended courses, store feedback by user/session, and expose aggregate signals the backend can use to tune ranking in later iterations; add validation and integration tests for feedback submission and retrieval.

