# Topic statement

The host view runs a linear UI pipeline from sign-in through spreadsheet parsing, preference-driven schedule generation, rating enrichment spinners, to a split-panel course presentation while mirroring intermediate artifacts in tab-scoped interactive state.

# Scope

- Covers page setup, gated main flow, sidebar memory management, parse button behavior, planning button behavior, recommendation fingerprint caching for rating refetch, display fallbacks, and keys cleared on logout.
- Excludes database schema details and vendor SDK internals.

# Data contracts

- **Session keys for planner flow:** missing gap list (`missing_details` from Excel parse), planning result dict, enriched recommendation list, fingerprint string for last enrichment, course-to-time map, last user preference message text, optional multi-line preference field value, mirrored numeric user id plus username for convenience.
- **Keys cleared on logout:** the gap list, planning result, enrichment list, enrichment fingerprint, course-to-time map, mirrored ids, preference field text, last user message text.
- **Planning result dict:** includes recommended array, total units, advice string, optional assistant reply string, optional warnings from generator.

# Behaviors (execution order)

1. Configure the page title and wide layout, load environment variables from a sibling dotenv file when present.
2. Require login; when unauthenticated, stop rendering the remainder.
3. Bind the numeric user id from the authenticated profile for memory calls.
4. Render title, sidebar signed-in label, logout control, upload control for progress spreadsheets, optional row-hiding toggle, and parse trigger.
5. In an expandable panel, list memory rows for the current user with delete buttons that remove one row or all rows then reload the view.
6. On parse click without a file, show a warning; with a file, parse bytes locally then show metrics, not-satisfied summary table, unique codes line, and full detail table optionally filtered to rows that have registration text.
7. After parse, overwrite the session gap list with the **gap-rows** list: for each `detail_rows` row whose **`status` equals the exact string `Not Satisfied`**, emit `{course, category, units}` where `course` is the parsed `course_code` (may be null), `category` is the requirement label, and `units` is taken verbatim from the row—same contract as `specs/03-planner-gap-rows-from-progress-parse.md` (this is **row-level** status, not the merged per-requirement overview bucket labeled “Not Satisfied”).
8. When a non-empty gap list exists, show step-two instructions, a preference text area, and a generate button.
9. On generate click with blank preference, warn; otherwise show a busy indicator, call the memory-augmented planning entrypoint with the current user id, gap list, trimmed preference, and prior planning result dict when already present, store returned dict and last user message on success, show a generic failure line on exception.
10. When a planning dict exists, optionally filter recommended rows to those whose course string matches any key in the base workbook map when that map is non-empty; if the map is empty, keep the model list unchanged.
11. Compute a stable fingerprint string of the filtered recommendations; when it differs from the stored fingerprint, run instructor enrichment in a busy state, store enriched list and new fingerprint; when filtered list empty, drop enrichment keys.
12. Render chat bubbles for the last preference text and assistant reply when either exists; if assistant reply empty, substitute advice text or a canned fallback sentence.
13. Split lower area into two columns: left shows bordered cards per enriched course with units, scheduled names caption, reason callout, rating metrics for the chosen top professor when data exists, otherwise warnings or informational notes; right shows recomputed unit sum from numeric course units when possible else generator total, then advice or an empty placeholder message.
14. When both filtered recommendations and enriched list are non-empty lists, compute the merged schedule map, show step-three divider, build weekday buckets per the calendar spec, render grid and pending list.
15. When gap list missing or empty, show informational text referencing needing prior analysis output.

# Error paths

- Authentication stop prevents duplicate rendering of protected sections.
- Parse with missing file warns only.
- Planning exception surfaces the exception message in an error component without updating the stored result on failure.
- Enrichment fingerprint logic skips network work when recommendations filtered to empty.
- Rating display branch shows unknown course labels, warns when professor list empty or error field set, skips metrics when best name missing, tolerates non-numeric ratings by showing dash styling.
- Total units in the summary column silently ignores non-numeric unit strings when summing.
