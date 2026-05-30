# Deployment — Plan A (Vercel frontend + Render backend)

**POC:** AdaL · **Updated:** 2026-05-29

## TL;DR

The app is a Vite/React SPA + a FastAPI backend that runs LLM planning
agents. Serverless functions (Vercel's Python runtime) time out on the
long planning requests, so we split the deploy:

- **Frontend (this SPA)** → **Vercel** (static build, global CDN).
- **Backend (FastAPI)** → **Render** (long-running web service, no
  function timeout).

The two are wired by environment variables only — no code change is
needed to point them at each other:

| Variable | Set on | Points at |
|----------|--------|-----------|
| `VITE_API_BASE` | Vercel | the Render API origin + `/api` |
| `FRONTEND_BASE_URL` | Render | the Vercel site origin |

Config lives in two committed files: `project/web/vercel.json` and
`render.yaml` (repo root).

---

## Step 1 — Deploy the backend to Render (do this first)

The frontend needs the API URL, so the API goes up first.

1. Render dashboard → **New → Blueprint** → connect this GitHub repo.
   Render reads `render.yaml` and provisions `course-planner-api`.
2. When prompted, fill the secret env vars (the ones marked
   `sync: false`):
   - `GEMINI_API_KEY` — your Google AI Studio key.
   - `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` — OAuth web-client creds.
   - `GOOGLE_OAUTH_REDIRECT_URI` —
     `https://<your-api>.onrender.com/api/auth/google/callback`
   - `FRONTEND_BASE_URL` — leave blank for now; fill after Step 2.
   - `SCU_PLANNER_COOKIE_KEY` — Render auto-generates this.
3. Deploy. Confirm `https://<your-api>.onrender.com/api/health` returns
   `{"status": "ok"}` (or similar).

> Free Render web services sleep after inactivity; the first request
> after a sleep takes ~30-60s to wake. Fine for a class demo; bump the
> plan for always-on.

## Step 2 — Deploy the frontend to Vercel

1. Vercel dashboard → **Add New → Project** → import this repo.
2. Set **Root Directory** to `project/web` (Vercel then picks up
   `vercel.json` and the Vite framework preset automatically).
3. Add one **Environment Variable**:
   - `VITE_API_BASE` = `https://<your-api>.onrender.com/api`
     (include the `/api` suffix; it is build-time, so a redeploy is
     needed if you change it).
4. Deploy. Note the resulting origin, e.g.
   `https://course-planner.vercel.app`.

## Step 3 — Close the loop (CORS + OAuth)

1. **Render** → `course-planner-api` → Environment → set
   `FRONTEND_BASE_URL` = your Vercel origin (no trailing slash). This
   adds it to the CORS allow-list (`_cors_allowed_origins` in
   `project/api/main.py`) and is used for OAuth redirects. Save → the
   service redeploys.
2. **Google Cloud Console** → Credentials → your OAuth web client →
   add the production redirect URI from Step 1.2 to **Authorized
   redirect URIs** (must match byte-for-byte).
3. Re-test sign-in end to end on the Vercel URL.

---

## Routing note

The SPA uses **hash routing** for sub-pages (`#/data-disclosure`, etc.),
so deep links work without rewrite rules. `vercel.json` still adds a
`/(.*) → /index.html` rewrite so clean-path deep links and OAuth
query-string returns (`/?google_oauth=...`) resolve to the SPA. See
`project/web/RENDER-SPA-ROUTES.md` for the equivalent Render notes.

## Local development is unchanged

`vercel.json` / `render.yaml` only affect the hosted builds. Locally you
still run the Vite dev server (proxying `/api` → `127.0.0.1:8000`) and
uvicorn per the root `AGENTS.md`.

## Why not all-Vercel?

Vercel's Python serverless functions cap execution (10s hobby / 60s pro).
The planning agents routinely exceed that on a cold model call, so a
long-running Render web service is the reliable home for the API. If you
later move to a fully async job + polling design, an all-Vercel deploy
becomes feasible.
