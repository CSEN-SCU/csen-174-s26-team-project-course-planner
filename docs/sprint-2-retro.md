# Sprint 2 Retrospective

## Celebrate

Ismael: Talking to the other group went well, it was nice being able to give and receive feedback. I was able to give feedback regarding responsible AI usage. I was then able to troubleshoot the data disclosure on our website to make sure anyone who accesses the website can see the disclaimer. I was also able to help get the Google sign in working on the Render site.

Jason: I shipped Google sign-in end-to-end—from the secure Streamlit flow through stateless OAuth + PKCE, to FastAPI/React with the handoff token—and then battled split-origin deployment on Render until the config matched reality. That’s real full-stack integration work under production constraints, not a demo checkbox.

Joey: I implemented both of the red team fixes. I added new pages including the Data Disclosure page, the Academic Progress Export page, Tutorial page, and Data Deletion page. Added general frontend UI improvements, such as drag and drop file uploading and the footer. Cleaned up and optimized repo, such as removing the old sign in feature.

Jiasheng: From the 18th to now, the headline work was re-architecting the SCU Course Planner from a single Gemini call into a full LangGraph multi-agent system, delivered as a clean five-step progression where each step landed as its own commit with tests. I started with a Planner → Verifier → InstructorSelector → Assembler graph prototype, then layered in capabilities one at a time: real instructor ratings so the selector ranks sections by quality (STEP A); a tool-calling ReAct Planner built on native Gemini function-calling — no langchain dependency — that decides for itself when to look up the schedule, resolve open Core requirements, or attach a lab co-requisite (STEP B); true parallel fan-out via LangGraph's Send API, running one instructor selector per course and merging results through a state reducer (STEP C); checkpointing plus a human-in-the-loop interrupt that pauses a plan for review before committing and survives a process restart via SQLite (STEP D); and finally HTTP wiring with POST /api/plan/v2, review/resume endpoints, and a feature flag that lets the legacy route delegate with zero frontend change (STEP E). The net result is three decision-making agents plus an assembler, nine callable tools, and four routing/decision points, all while leaving the original engine untouched.
Alongside the agents, I built a reproducible evaluation harness — seven deterministic, rule-based scorers (no hallucinated courses, no time conflicts, lab pairing, unit caps, correct titles, open-Core coverage, no prompt-injection leakage) with an A/B runner to compare engines objectively, deliberately avoiding LLM-as-judge so scoring stays reproducible and is itself unit-tested. In the middle of this, while recovering a test suite that an earlier rebase had silently dropped, the recovered tests immediately surfaced a real production bug a teammate's edit had introduced: memory_agent.write() was storing the wrong content on every write, which had quietly broken memory persistence for all logged-in users — I fixed it and verified the fix end-to-end through the live API. I also wrote the supporting documentation: an AGENTS.md at the repo root codifying the SCU domain rules so future agents read them before editing, a self-contained HANDOFF.md so another LLM can pick up the work cold, and a README section documenting the LangGraph architecture, endpoints, and how to run the eval.
In total that's roughly ten pushed commits, the complete A-through-E LangGraph track, and around ninety passing tests across the multi-agent and eval work, plus the recovered planning-agent and memory test suites. The one caveat for the summit is that the live A/B eval run comparing the legacy and multi-agent engines on real Gemini calls got interrupted, so I don't have final head-to-head numbers yet — the harness is ready and I can run it in a few minutes if you'd like hard figures to quote on stage.


## Red Team Response

Our team received feedback that we had problems primarily with prompt injection and data privacy concerns. We decided to deal with these issues right away since they were easy to fix and so that they wouldn’t come up later. For the prompt injection we added more system instructions stating the purpose of the application and added to treat user prompts as an unprompted source. We implemented this in the backend to ensure that a malicious user can't modify the system instructions before the website. For data privacy concerns, we added a data disclosure page that can be seen by clicking on a link at the bottom of our home page. This explicitly states how user data is processed so that users can make the most informed decisions possible.

(https://github.com/CSEN-SCU/csen-174-s26-team-project-course-planner/pull/26)[https://github.com/CSEN-SCU/csen-174-s26-team-project-course-planner/pull/26]

(https://github.com/CSEN-SCU/csen-174-s26-team-project-course-planner/pull/27)[https://github.com/CSEN-SCU/csen-174-s26-team-project-course-planner/pull/26]

## Sprint 3 Commitments:

### Commitment 1: Add a guide for how to use the tool

For this, we want to add a guide for how to use our tool. Currently, we have a skeleton across the different pages found in the footer, but we would like this to be more cleanly integrated into the User Interface. We would like a unified guide to be accessed by clicking on a circle with a question mark in it that is by some corner of the site. 

(https://github.com/CSEN-SCU/csen-174-s26-team-project-course-planner/issues/30)[https://github.com/CSEN-SCU/csen-174-s26-team-project-course-planner/issues/30]

### Commitment 2: Optimize homepage UI design 

Right now the homepage when opening the website has a lot of empty white space. We plan to make this more visually appealing by adding larger text, pictures, and some links to guides or FAQs.

(https://github.com/CSEN-SCU/csen-174-s26-team-project-course-planner/issues/31)[https://github.com/CSEN-SCU/csen-174-s26-team-project-course-planner/issues/31]

We will also try to implement features that we are missing during this week since we have a lighter work load. We plan to take advantage of this by implementing any pending Kanban boards that we have along with any new features we think of. We will try to polish everything so that the following weeks we just have to make small changes and tweaks.
