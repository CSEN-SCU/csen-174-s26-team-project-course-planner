# Topic statement

After a progress workbook parse, the interactive host replaces the planner gap list with one object per detail row whose status string exactly matches the unsatisfied literal used in the export.

# Scope

- Covers only the transition from parsed detail rows into the list consumed by schedule generation in the main flow.
- Excludes merged requirement summaries shown in overview tables, the separate document-driven gap module, and any model calls.

# Data contracts

- **Each gap item:** `course` taken from the parsed `course_code` field (may be null if unparsed), `category` taken from the requirement label, `units` taken verbatim from the sheet cell (type preserved).
- **Trigger:** user activated the parse action and a file was present; replacement happens on that same run after tables are rendered.

# Behaviors (execution order)

1. Read the latest `detail_rows` collection from the parse output.
2. Filter to rows whose `status` field equals the exact string `"Not Satisfied"`.
3. Map each kept row to a trio of course, category, units.
4. Write the resulting list into the interactive session under the key used by the scheduling step.
5. If the user never successfully parsed with a file, this list is absent or stale from an earlier session until overwritten.

# Error paths

- No file on parse click shows a warning; the gap list is not refreshed on that click.
- Rows with not satisfied status but no parseable course code still produce entries with a null course field; downstream scheduling still receives them.
- If parsing threw before returning, the host never reaches the assignment; prior session list may remain.
