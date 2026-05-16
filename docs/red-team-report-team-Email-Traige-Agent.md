## Our Target: SCU Course Planner

### Summary

Our target is a course-planning assistant for Santa Clara University students: it ingests Academic Progress exports, optionally syncs Workday, and uses Gemini-backed agents to recommend next-term schedules, four-year plans, and conversational help. We reviewed the public repository layout (`project/api`, `project/web`, `project/course_planner`), the FastAPI routes and routers, the Vite/React client, and agent prompt construction in `planning_agent.py` and related modules. We exercised the deployed or locally running application through the chat UI, repeated API-style actions such as rapid regeneration, and manual prompt-injection strings.

Screenshots in this `docs/` folder document UI failures, empty plans, Workday sync errors, and model behavior under adversarial prompts. Cursor-assisted code review complemented dynamic testing to tie each finding to concrete surfaces such as routes, lack of auth or rate limits, and prompt assembly.

### Threat Model

- **Casual or curious student** — Mis-clicks, spamming controls, or pasting odd text into chat; can accidentally trigger cost, broken state, or confusing AI output without malicious intent.
- **External opportunistic attacker** — Anyone who can reach the API if exposed beyond localhost can probe unauthenticated or IDOR-style patterns: weak session binding on `user_id`, no rate limits on planning endpoints, and expensive LLM or Playwright paths.
- **Prompt-injection or data-poisoning actor** — Supplies transcript-shaped JSON, chat text, or memory-like content intended to override instructions, extract system framing, or steer recommendations away from policy.
- **Insider or compromised client** — A modified frontend could send crafted `missing_details` or arbitrary `user_preference` payloads; the server trusts much of that structure for model context.

---

## Technical Security

### 1) Missing or Insufficient Rate Limiting and Abuse of Planning Endpoints

**Where:**

- `project/api/main.py` — FastAPI app mounts routers without global throttling middleware.
- `project/api/routers/plan.py` and `project/api/routers/four_year_plan.py` — POST handlers invoke Gemini agents per request.
- Observed in UI: rapid use of regenerate or equivalent plan actions during red-team session.

**Reproduction steps:**

1. Log in and upload a valid Academic Progress file so planning is enabled.
2. Trigger plan generation repeatedly in quick succession (for example spam regenerate or send many plan requests from the chat flow).
3. Observe elevated latency, quota errors, or degraded UI state; team reported that after heavy spam the app became unusable and the interface repeatedly prompts to upload a file.

**Severity:** Major (availability and cost; severity rises to Critical if the API is Internet-exposed without auth).

**Why it matters:**

Unbounded client-driven calls to LLM-backed endpoints allow denial-of-wallet, denial-of-service for other users sharing the same API key, and client UX collapse when error handling maps failures to a generic upload-a-file state. Attackers may not need credentials if routes are reachable without strong limits.

**Recommendation:**

Add per-IP and per-user or per-session rate limits on `/api/plan`, `/api/four-year-plan`, and related expensive routes; return HTTP 429 with a clear `Retry-After`. Cap concurrent in-flight jobs per user. On upstream quota failures, distinguish try again later from session lost so the UI does not trap users in a false upload loop.

### 2) Fragile Session and Memory UX After Login (Conversation and Transcript State Not Restored)

**Where:**

- `project/web/src/App.tsx` and chat or memory integration — client holds `user_id` and local message state; transcript and `missing_details` appear tied to current browser session flow rather than durable server-side session on every login.
- `project/api/routers/memory.py` — memory keyed by `user_id` string; red-team concern is consistency of expectations versus enforcement.

**Reproduction steps:**

1. Register or log into an existing account; complete upload and chat.
2. Log out or refresh in a way that clears client state; log in again with the same account.
3. Observe chatbot prompting to upload again and not surfacing prior conversation context (team observation).

**Severity:** Moderate (privacy expectations versus actual behavior; product integrity).

**Why it matters:**

Users may believe conversations and uploaded progress are account-persistent. Reset-to-upload messaging after legitimate re-login looks like data loss or a bug, erodes trust, and may encourage risky workarounds such as re-uploading or screenshotting sensitive exports.

**Recommendation:**

On successful login, fetch server state (`missing_details` snapshot, memory list) and hydrate the UI; persist minimal server-side flags for transcript loaded for user X. Document clearly what is stored where. If memory is intentional, gate reads behind authenticated session ownership.

### 3) Workday Sync Failure (Operational and Trust Break)

**Where:**

- `project/api/routers/workday.py` — POST `/api/workday/sync`, background thread and Playwright scraper.
- `project/course_planner/utils/workday_scraper.py` — browser automation and export flow.

**Reproduction steps:**

1. From the UI, start Workday sync (or call POST `/api/workday/sync` with a test body).
2. Observe job status errors, timeout, or browser or Playwright failures depending on environment (headless versus visible, SSO, URL configuration).
3. Capture screenshot or JSON from GET `/api/workday/status/{job_id}` showing error state.

**Evidence:**

![Workday sync failed with missing Playwright dependency](sync_screenshot.png)

**Severity:** Low (feature reliability; higher if users rely on sync instead of manual upload of sensitive files). *Not very serious as just simply not implemented yet.*

**Why it matters:**

Failed sync pushes users toward manual xlsx handling or retries; error payloads may leak internal exception strings. Unauthenticated sync start in the current API design is also abusable if exposed publicly.

**Recommendation:**

Harden error messages for clients; require authentication before starting sync; validate `workday_url` against an allowlist. Provide actionable user messaging such as SSO timeout or export button moved without raw stack traces.

### 4) New Plan Control Does Not Reset Plan State as Users Expect

**Where:**

- Frontend navigation and plan reset (team: New Plan button); planning state likely lives in React state without full reset path except via chat.

**Reproduction steps:**

1. Generate a plan from chat.
2. Click New Plan or equivalent and observe whether schedule and messages clear and a fresh planning session starts without relying on chat commands.
3. Compare to creating a new plan only through chat (team: only chat path works reliably).

**Severity:** Minor to Moderate (UX and potential confusion leading to duplicate API calls or wrong assumptions).

**Why it matters:**

Inconsistent controls increase accidental double submissions and support burden; users may think they cleared sensitive on-screen data when they did not.

**Recommendation:**

Wire New Plan to the same reset handler as the documented chat flow: clear `planResult`, `missingDetails` only when intended, messages, and any cached `previous_plan` sent to the API.

---

## AI API Security

### 1) Four-Year Plan Scope Blind to Electives and Long-Horizon Preferences

**Where:**

- `project/course_planner/agents/four_year_planning_agent.py` — plan built from `missing_details` (remaining requirements) and optional preferences string.
- `project/api/routers/four_year_plan.py` — passes client-supplied `missing_details` and preferences to the agent.

**Reproduction steps:**

1. Upload progress for a student with many remaining requirements and elective goals not represented as rows in `missing_details`.
2. Ask the four-year planner to optimize electives or horizons beyond the encoded requirement list.
3. Observe output that only distributes known rows and ignores unstated elective intent (team finding).

**Evidence:**

![Assistant refuses to add a different elective to the four-year plan](four_year_screenshot.png)

**Severity:** Moderate (product correctness and Responsible AI alignment — misleading completeness).

**Why it matters:**

The model can appear authoritative while omitting student goals not present in structured data. Newer students may get under-filled plans and incorrect confidence.

**Recommendation:**

Separate degree requirements from student goals in the schema; pass explicit elective slots or free-text goals with validation. Add UI copy that the multi-quarter plan covers exported requirement rows only.

### 2) Four-Year Plan Intermittently Empty or Unstable Output

**Where:**

- `project/course_planner/agents/four_year_planning_agent.py` — JSON parsing, model fallbacks, `ValueError` paths.
- `project/api/routers/four_year_plan.py` — surfaces errors as HTTP 502 or 500 with `detail=str(exc)` in places.

**Reproduction steps:**

1. Call POST `/api/four-year-plan` repeatedly with the same valid `missing_details` payload (optionally under load or with marginal payloads).
2. Observe occasional empty or invalid responses versus plausible multi-quarter JSON.
3. Capture response body and server logs if available.

**Evidence:**

![Four-year plan grid with empty quarters and zero scheduled units](four_year_misfunction_screenshot.png)

**Severity:** Major (core feature unreliable).

**Why it matters:**

Non-deterministic empty plans waste user time and may cause users to dismiss the tool as broken; combined with weak error text, users may expose more data through repeated retries.

**Recommendation:**

Strict response validation; when parse fails, return a structured error and never render an empty grid as success. Add idempotent request keys and short server-side caching for identical payloads to reduce duplicate model spend.

### 3) LLM Prompt Injection via Chat (`user_preference`) and Structured Context

**Where:**

- `project/course_planner/agents/planning_agent.py` — `user_preference` and JSON serialization of `missing_details` embedded in the user-facing prompt; `memory_snippets` in a delimited block with budget but not cryptographic separation.
- `project/api/routers/plan.py` — conversational branch `_answer_conversational` also forwards user text to the model.

**Reproduction steps:**

1. With a normal transcript loaded, send chat text that attempts instruction override (for example ignore prior rules, request disallowed output format, or ask the model to contradict the schedule schema).
2. Observe whether `assistant_reply`, `advice`, or JSON fields drift from policy or break self-consistency checks.
3. Document screenshots.

**Evidence:**

![Prompt injection: model includes burrito instructions in the advice section](prompt_injection_screenshot.png)

**Severity:** Major (integrity of planning output; severity depends on downstream trust in the UI).

**Why it matters:**

User text is untrusted; without output validation and strong delimiters, attackers or malicious pasted content in preferences can steer tone, compliance, or attempt exfiltration of instructions within the model context window.

**Recommendation:**

Treat model output as untrusted: validate JSON schema strictly, strip or sandbox `assistant_reply` for dangerous patterns, and continue mitigations already partially present (memory char budget, CURRENT ASK wins wording) with automated tests on injection strings.

### 4) Prompt Injection Aimed at System or Developer Instruction Exfiltration or Mirroring

**Where:**

- Same prompt assembly as above; `system_instruction` in `planning_agent.py` and `four_year_planning_agent.py` is not visible to end users but may be partially echoed if the model is jailbroken.

**Reproduction steps:**

1. Craft chat prompts that ask the model to repeat hidden instructions, system prompts, or internal policies verbatim.
2. Compare model replies to actual `system_instruction` strings in repository (red-team: confirm leakage path).
3. Archive screenshots for responsible disclosure.

**Evidence:**

![Model echoes internal precedence rules from the system prompt](prompt_injection_2_screenshot.png)

![Repository source for the leaked precedence block in `planning_agent.py`](prompt_injection_3_screenshot.png)

**Severity:** Moderate to Major (information disclosure about prompt structure aids further attacks; usually not direct credential leak).

**Why it matters:**

Leaked system prompts reveal exact guardrails, schema hints, and vendor-specific wording, lowering the cost for tailored follow-on injections.

**Recommendation:**

Periodic red-team suites against `user_preference`; log and alert on anomalous completion patterns; avoid putting secrets in system prompts. Consider server-side post-filters that block large verbatim repeats of known instruction blocks.

---

## Responsible AI

Course planning tools handle FERPA-adjacent academic data: remaining requirements, grades in full exports even if not all fields are sent to the LLM by default, and user preferences about health, workload, or life circumstances typed into chat. When the app forgets context after login, shows empty plans, or misstates what the four-year view covers, users may over-trust or under-trust the system in ways that affect enrollment decisions. Prompt-injection successes, even partial, undermine the idea that the assistant is a predictable extension of DegreeWorks.

We recommend:

1. Clear in-product disclosure of what data is sent to Google Gemini and for how long.
2. Opt-out or minimize PII in free-text preferences.
3. Human-in-the-loop confirmation before any future feature that could auto-submit enrollment changes.
4. Alignment between UI buttons such as New Plan and actual data lifecycle so users understand when local versus server memory clears.
