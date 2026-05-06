# Sprint 1 — CI/CD and live deployment (Week 6)

Submit this document with your Camino submission (repo URL + this write-up). Replace every `<!-- ... -->` placeholder with your team’s real content.

---

## Part 1: GitHub Actions CI (4 pts)

### Merged PR with passing CI

- **PR link:** <!-- e.g. https://github.com/CSEN-SCU/csen-174-s26-team-project-course-planner/pull/NN -->
- **What the workflow does (one sentence):** <!-- On every push/PR to main, it … and runs … -->

### Secrets handling (3–5 sentences)

<!-- Fill in:
- Which secrets exist (names only, never paste values): e.g. GEMINI_API_KEY, DATABASE_URL for CI, etc.
- Where each is stored: GitHub Actions (Settings → Secrets and variables → Actions) vs Render (or other host) environment.
- Which surface needs which secret (CI only, deployment only, or both).
- How the workflow references them: e.g. ${{ secrets.NAME }} in the workflow YAML.
- One line on how you avoided committing secrets (no .env in repo, etc.).
-->

---

## Part 2: Live deployment (4 pts)

### Live URL

- **Public URL:** https://csen-174-s26-team-project-course-planner.onrender.com

### Deployment platform screenshot

Successful deploys (Render dashboard):

![Static site — frontend deployments](courseplannerfrontend.jpg)

![Web service — API deployments](courseplannerbackend.jpg)

### Platform choice paragraph (3–5 sentences)

When deciding which platform to use, we asked Cursor which option fit how our project works. It recommended Render among the platforms listed in the assignment because it supports full-stack setups, gives us a public URL, and exposes a clear Deployments view for screenshots. One source of confusion at first was that we set up the static site first but did not initially add a Web Service for the backend. That left only the frontend running, so there was no server to handle transcript parsing. Once we added the API service and configured environment variables (including API keys), the app worked end-to-end.

---

## Checklist before deadline

- [ ] URL loads with no server error; core entry point (home / main UI) is visible.
- [ ] Site stays up in the **24 hours** before the deadline (avoid last-minute only deploys).
- [ ] All deployment secrets are only in the host’s environment, not in code or committed `.env`.
- [ ] If you use a separate API, `CLIENT_ORIGIN` on the API matches the **exact** frontend origin (no trailing slash).

---

## Related assignment file

- Sprint 1 retrospective (Part 3 only): `docs/sprint-1-retro.md` — create separately when you do the retro.
