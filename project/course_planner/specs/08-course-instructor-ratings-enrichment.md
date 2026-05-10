# Topic statement

Each recommended course row is expanded with instructor names plus aggregate teaching scores by consulting a public ratings network with optional alignment to a local course-section workbook.

# Scope

- Covers department inference, school resolution, paginated professor discovery, scheduled-instructor-first paths, parallel per-course work, and graceful degradation when the optional client package is absent.
- Excludes weekly calendar placement and unit arithmetic.

# Data contracts

- **Input row:** planner-shaped object with at least a course string and optional category string.
- **Output row:** copies all input keys plus `professors` list of objects with name, overall quality score, difficulty score, would-take-again percent string; `best_professor` name string or null; optional `scheduled_instructors` string list when the section index matched; optional `rmp_note` human explanation; optional `error` string on hard failures.
- **Host presentation:** the signed-in planner renders every professor in `professors` in a per-course table sorted by overall rating descending (missing ratings last), with difficulty and would-take-again columns; `best_professor` is labeled when it matches a row.
- **Section index:** mapping from subject-number pairs to ordered unique instructor display names, with lab-row names merged onto base catalog numbers and mirrored electrical-subject aliases.

# Behaviors (execution order)

1. Return an empty list immediately when the input list is empty.
2. When the optional ratings client import failed at module load, return one output row per input with empty professors, null best pick, and a note explaining the dependency is missing.
3. Load the section index from the first existing default-named workbook beside the application package, or an empty map when none exist or required column headers are missing.
4. Choose a parallel worker count capped at six and at least one, then map each input course through enrichment independently.
5. For each course, start with empty professors and null best; derive scheduled names from the index keys implied by tokenizing the course string with cross-listed subject aliases.
6. Open a fresh ratings client per course inside the worker, resolve the university’s numeric school id by searching the network for the full school name then falling back to a hard-coded id when search fails or returns empty.
7. **Scheduled path:** when at least one scheduled instructor name exists, store that list on the output, look up each unique name via last-name search on the school listing, accept a match when full lowercased names equal or last names equal with same first initial, score each resolved profile with paginated recent reviews weighted by whether review text mentions expected catalog tokens and subject abbreviations, sort by evidence score then rating descending, serialize to dicts, set best to the first list entry’s name even when that entry lacks numeric scores, attach a note when any scheduled person lacks a profile or when evidence score for the top hit is zero.
8. **Unscheduled path:** infer lowercase department keywords from subject prefix maps and category text; if nothing inferred, set a note about manual lookup and return.
9. Paginate the school-wide professor listing without a name query up to many pages, collecting unique entries whose department string contains any inferred keyword or the lowercased subject prefix.
10. When that search yields nobody, set a note about no department match and return.
11. Rank a preliminary slice by presence of rating then numeric rating, compute per-professor evidence from review pages capped to a small page count, take the top few by evidence then rating, serialize; if top evidence is zero, add a disclaimer that the list is same-department reference only.
12. On any unexpected exception in the per-course try block, capture the exception text in `error` and return the partial object.

# Error paths

- Missing optional package: uniform note on every row, no network calls.
- Missing workbook file: empty index drives the unscheduled department path for every course.
- Malformed workbook: missing headers yields empty index, same as absent file.
- Network or API exceptions per course become the `error` string while other fields may remain partial.
- Last-name search shorter than two characters skips lookup and yields no match for that instructor.
