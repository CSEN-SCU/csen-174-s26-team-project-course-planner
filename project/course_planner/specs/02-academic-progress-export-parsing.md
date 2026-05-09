# Topic statement

An uploaded binary workbook representing a single-column academic progress export is transformed into tabular detail rows plus rolled-up requirement statistics.

# Scope

- Covers reading the active sheet, locating the header row, interpreting subsequent rows, extracting course codes from registration text, and aggregating status counts per requirement label.
- Excludes building the planner’s gap list, UI rendering, and any network calls.

# Data contracts

- **Input:** raw bytes of one workbook in the expected export layout.
- **Output bundle:**
  - `detail_rows`: ordered list of objects with requirement label, row-level status string, remaining field (string, number, or absent), registration cell text or absent, parsed course code or absent, academic period, units, grade.
  - `not_satisfied`: one summary entry per requirement whose merged block status equals the literal `"Not Satisfied"`, each carrying requirement label, remaining from an exemplar row, and status `"Not Satisfied"`.
  - `course_codes`: sorted unique list of every parsed code collected from registration rows.
  - `requirement_status`: mapping from requirement label to a single merged status string per block.
  - `requirement_status_counts`: counts of requirement labels by merged status.
- **Course code extraction:** leading clause before an em dash separator; parenthetical fragments containing specific phrases about transfer or in-progress are stripped first; subject must be two to eight Latin letters; catalog token must be digits with optional trailing letters; result is uppercase subject plus space plus uppercase catalog.

# Behaviors (execution order)

1. Open the workbook read-only from memory and select the active worksheet iterator.
2. Scan rows until the first cell equals the exact header token that marks the start of data.
3. For each subsequent row, skip completely empty leading columns; skip rows whose requirement label is blank after trimming.
4. Read up to seven logical columns into structured fields, coercing blanks to empty strings except remaining and registration which may stay absent.
5. Accumulate every distinct raw status string seen for each requirement label into a set.
6. Whenever registration text parses to a code, append that code to an all-codes list.
7. Append a detail object for every non-skipped row regardless of whether a code could be parsed.
8. After all rows, merge each requirement’s status set with priority: any `"Not Satisfied"` wins, else any `"In Progress"`, else the lexicographically smallest remaining status if multiple.
9. For each requirement whose merged status is `"Not Satisfied"`, choose an exemplar detail row preferring one whose own row status is also `"Not Satisfied"`, otherwise the first row for that requirement, and push a summary object.
10. Close the workbook even when iteration ends early.
11. Deduplicate and sort collected codes by subject then catalog token.
12. Count how many requirement labels ended in each merged status bucket.

# Error paths

- Missing or wrong header means no rows are treated as data; outputs are mostly empty structures.
- Malformed registration text yields `course_code` null on that row without aborting the parse.
- Workbook IO or parser failures propagate to the caller (not swallowed inside this module).
