# Render: client routes (Data Disclosure, future onboarding)

## What you need on Render today: **nothing**

The app uses **hash routing** for Data Disclosure:

- Footer link: `#/data-disclosure`
- Full URL example: `https://your-frontend.onrender.com/#/data-disclosure`

Render always serves `/index.html` for the site root. Hash changes are handled entirely in the browser, so you do **not** need Redirect/Rewrite rules for disclosure to work.

`public/_redirects` is for Netlify-style hosts only — **Render ignores it.**

## Google OAuth

After sign-in, Google redirects to `https://your-frontend.onrender.com/?google_oauth=...` (root + query string). That path is also served by `index.html` with no extra config.

## Optional: clean URL `/data-disclosure` (no `#`)

Only add this if you want shareable links **without** the hash. It is **not required** for the footer link to work.

1. Render dashboard → your **static site** service → **Redirects** / **Redirects/Rewrites**
2. Add:
   - **Source:** `/*`
   - **Destination:** `/index.html`
   - **Action:** **Rewrite** (not Redirect)
3. Save and redeploy if prompted.

`Root.tsx` already recognizes both `#/data-disclosure` and `/data-disclosure` when that rewrite exists.

## Future onboarding slides

When you add a forced first-visit modal, prefer a hash route (e.g. `#/welcome`) or in-app state only — same pattern as disclosure — so you avoid new Render rules per screen.
