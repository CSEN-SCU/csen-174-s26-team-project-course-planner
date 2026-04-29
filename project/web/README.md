# Ismael Prototype Frontend

Transcript-first SCU Course Planner prototype built with React, Vite, TypeScript, and Tailwind.

## Features

- Intro/landing screen with quick "what/for whom/problem/how" explanation.
- Transcript upload flow with parsed summary.
- Eligible-course filtering (type, division, requirements, time window).
- Priority mode ranking: Balanced, Quality-first, Easier workload.
- Course results table with fit score and section/professor details.
- Schedule building with soft conflict warnings (red highlight, still addable).
- Calendar tab that preserves in-memory schedule state.
- AI assist actions for recommendation and partial schedule completion.
- Export controls for Google Calendar UX + `.ics` fallback.

## Run locally

```bash
cd prototypes/ismael/web
npm install
npm run dev
```

Then open the local URL shown by Vite (typically `http://localhost:5173`).

## Backend integration

Set `VITE_API_URL` in a local `.env` file if your API is not at `http://localhost:8080`.

Example:

```bash
VITE_API_URL=http://localhost:8080
```

If backend routes are unavailable, the UI gracefully falls back to realistic mock responses.
