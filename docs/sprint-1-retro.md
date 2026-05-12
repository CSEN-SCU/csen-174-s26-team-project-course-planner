# Sprint 1 Retrospective

## What went well in Sprint 1?

In Sprint 1, we built a sustainable development workflow for the project. We first organized our project ideas and split work ownership into multiple systems, as defined at the bottom of `architecture/architecture.md`. We then set up the testing suite in the `project/course_planner/tests` folder so that we could automatically validate our work. Lastly, we began to work on the features and functionality of the project with a new frontend and backend that will be used for the final product. On the AI implementation side, we made schedule generation more operationally robust: explicit handling when the model provider is misconfigured or overloaded, tests that encode the expected contract, and a path to extend planning features without breaking existing behavior.


## What could be improved?

During Sprint 1 we delivered tests, basic security, and a foundation for the final project, but we still have many features left to implement. Right now the app feels closer to a single-session experience: we cannot reliably isolate preferences and planning data per user, and LLM context does not persist across repeated usage. That's the functionality we will focus on during the next Sprint. We feel we could spend more time dedicated to adding these features outside of course and the lab sections, which we mainly spend on the assignments. During Sprint 2, we would like to see a better mix of general progress and assignment work so that both progress well. 

AI implementation improvements:
Observability for AI failures: clearer user-facing copy + logging/metrics when Gemini returns 503 / empty responses, so support and demos don’t depend on guessing. 
Evaluation, not only correctness tests: lightweight checks that recommendations stay on-policy (e.g. units caps, no hallucinated course codes) before we add explainability (#12) and feedback (#13).

## Celebrate

| Member | Specific contributions |
|---|---|
| **Jiasheng** | Added rate my professor API to LLM recommendation system, added feature that pattern match user's transcript to fetch.  |
| **Jason** | Implemented and hardened AI-backed schedule generation in the main planner: provider selection and safe fallback when Gemini is unavailable or rate-limited so users get a predictable response instead of a hard failure; added automated tests under project/tests/jason/ to lock in provider/fallback behavior and red tests for upcoming planning API behavior so we can extend the AI surface without regressions. (If you also shipped resilience in project/course_planner — e.g. retries / model fallback on 503 — add one short clause: “Added retry + fallback model behavior for transient Gemini 503s.”  |

| **Ismael** | Implemented Vitest and Testing Library under project/web, added owner-scoped test scripts and project/tests/README.md so the frontend suite runs from project/web. Added project/tests/ismael/iy_plannernav_accessibility.test.tsx, which checks that when Build is the active planner tab, that tab’s button exposes aria-current="page" so screen readers can tell which section of the planner is selected—not only visual styling. That check started RED because PlannerNav did not set aria-current; implementing aria-current on the active tab (and type="button" on tab buttons) made the test GREEN.

| **Joey** | Ported test suite from initial project based on Ismael's prototype, found in the `project` directory, to the final project location in the `project/course_planner` directory. In addition, consolidated tests from a tests and api/tests folder into one tests folder. This corrected a mistake we made during week 5, where we wrote our test suite for the initial project on top of Ismeal's prototype, rather than the new project base. This consolidation allowed us to continue using our necessary testing in the final code location. |

## AI tools reflection

AI tools were most helpful for developing the test suite during Sprint 1. Using Cursor and Claude, we generated a lot of test scaffolding quickly using the Arrange/Act/Assert design discussed in class. For example: session cookie security flags, password storage properties like unique salts and verification behavior.

We also faced some challenges using AI tools during this Sprint. We ran into some cases of hallucination, where AI improperly created or solved a test. For example, when asking it to create a Database test, it would also create the database even though it was not prompted to do so. Another example was AI inventing fake APIs that looked plausible but failed to run. We had to keep these in mind and not just blindly run code as written.

## Sprint 2 Commitments

In Sprint 2, we commit to extending our Sprint 1 foundation with the features in our project plan. Each commitment maps directly to a Kanban card:

1) **Integrate the 4-Year Plan feature into the main workflow**  
   - Kanban card: [Issue #5 — Integrate 4 Year Plan Feature](https://github.com/CSEN-SCU/csen-174-s26-team-project-course-planner/issues/5)  
   - What we will do: define the 4-year plan data model and UI entry points; add tests for key flows (at minimum: create/edit and a primary “view/export” path) so existing behavior stays stable as we ship new functionality.

2) **Add a user account system**  
   - Kanban card: [Issue #6 — Add User Account System](https://github.com/CSEN-SCU/csen-174-s26-team-project-course-planner/issues/6)  
   - What we will do: implement a minimum viable account + session flow; define acceptance criteria for user data isolation; add end-to-end coverage (each user sees only their own data, correct behavior after logout/session expiration).

3) **Add a per-user RAG/memory database**  
   - Kanban card: [Issue #9 — add RAG database for user](https://github.com/CSEN-SCU/csen-174-s26-team-project-course-planner/issues/9)  
   - What we will do: bind memory storage/retrieval to a userId; implement a minimal retrieval chain (write → retrieve → inject into prompts/context); add tests and basic guardrails to prevent cross-user leakage (retrieve only current user memory, controllable top-k and context length limits).

4) **Add AI recommendation explainability fields and confidence rationale**  
   - Kanban card: *(https://github.com/CSEN-SCU/csen-174-s26-team-project-course-planner/issues/12)*  
   - What we will do: extend schedule API responses with short, user-readable explanation fields per recommended course (why it was selected, tradeoffs, and confidence rationale) so students can trust recommendations; add contract tests to ensure explanation fields are always present and non-empty.

5) **Add user feedback loop endpoint for recommendation quality tuning**  
   - Kanban card: *(https://github.com/CSEN-SCU/csen-174-s26-team-project-course-planner/issues/13)*  
   - What we will do: implement an endpoint for thumbs-up/down and swap reasons on recommended courses, store feedback by user/session, and expose aggregate signals the backend can use to tune ranking in later iterations; add validation and integration tests for feedback submission and retrieval.

