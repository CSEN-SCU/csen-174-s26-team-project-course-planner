# Sprint 2 — Red Team Report Remediations

---

## Remediation 1: Added Data Disclosure Page

**Peer finding:** In the Responsible AI section, they noted that we are handling potnetialy sensitive student academic information. As such, it is important that the know how their data will be handled.

- **Source finding:** Responsible AI Section suggestion #1 from: [red-team-report-team-Email-Traige-Agent.md](red-team-report-team-Email-Traige-Agent.md)  
- **Merged PR:** [https://github.com/CSEN-SCU/csen-174-s26-team-project-course-planner/pull/27](https://github.com/CSEN-SCU/csen-174-s26-team-project-course-planner/pull/27)
- **What changed:** Added a separate data disclosure page to the front end that explicity states what data is used by the Gemini API. As suggested, this adds a "clear in-product disclosure" of what data from the user's documents and prompts are kept and processed.


## Remediation 2: Implemented Prompt Injection Prevention

**Peer finding:** In the LLM Prompt Injection section, they were easily able to get the Gemini API to output information irrelevant to SCU Course Planner, which could led to users exploiting free access to our API key for their own outside purpose.

- **Source finding:** 3) LLM Prompt Injection via Chat (user_preference) and Structured Context Section from: [red-team-report-team-Email-Traige-Agent.md](red-team-report-team-Email-Traige-Agent.md)  
- **Merged PR:** [https://github.com/CSEN-SCU/csen-174-s26-team-project-course-planner/pull/28](https://github.com/CSEN-SCU/csen-174-s26-team-project-course-planner/pull/28)
- **What changed:** Added prompt injection prevention, such as by explicitly including insturctions to not repeat system prompts and to treat the user input asa untrusted. 
