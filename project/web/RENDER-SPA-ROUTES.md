# Render: `/data-disclosure` and other client routes

Render **does not** read Netlify-style `public/_redirects` files. A link to `/data-disclosure` returns **404 Not Found** unless you add a **Rewrite** rule.

The app footer uses `#/data-disclosure` so **Data Disclosure works without any dashboard change**.

## Optional: clean URL `/data-disclosure` (no `#`)

In the Render dashboard for the **static site** service:

1. Open the service → **Redirects** (or **Redirects/Rewrites**).
2. Add a rule:
   - **Source:** `/*`
   - **Destination:** `/index.html`
   - **Action:** **Rewrite** (not Redirect)
3. Save and redeploy if prompted.

Then `https://your-site.onrender.com/data-disclosure` loads the SPA and `Root.tsx` can show the disclosure page.
