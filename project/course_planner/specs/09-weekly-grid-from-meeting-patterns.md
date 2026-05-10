# Topic statement

Recommended courses with enriched metadata are grouped into weekday columns using meeting time strings pulled from the local sections workbook plus any meeting strings copied from enriched recommendations onto alternate course-code keys.

# Scope

- Covers building the course-to-raw-pattern map, filtering recommendations against that map, parsing day tokens and time ranges, assigning cards to weekday buckets, and listing leftovers.
- Excludes rating fetch and chat transcript rendering.

# Data contracts

- **Meeting pattern string:** free text expected to contain a day token list, a vertical bar, then a start and end clock time; extra hyphen characters in the time tail are allowed—the implementation takes the first and last time-like tokens (e.g. `10:00 AM - 11:00 AM - lab - 12:30 PM`).
- **Parsed schedule fragment:** list of day keys after tokenization (`Th` is consumed before a bare `T` so `TTh` yields Tuesday then Thursday), start time string, end time string.
- **Day index map:** Monday through Friday mapped to integer column positions; Thursday is represented by `Th` or by the single letter `R` (common alongside `T` for Tuesday).
- **Course schedule map:** uppercased subject-number keys to raw meeting pattern text, seeded from workbook rows, then augmented so every variant key for a recommended course shares the same pattern string, including a key that preserves the planner’s original spacing when variants differ.

# Behaviors (execution order)

1. Load base workbook rows into a code-to-pattern map using the section column and meeting column; stop scanning after the first successfully opened default filename in a fixed try order; return empty map when no file or missing headers.
2. When session holds a list of enriched recommendations, for each item’s course string derive variant codes (slash combos, cross-listed subjects, concatenated subjects without spaces) and copy whichever pattern already exists for any variant onto all variant keys and onto the display-spaced original string key.
3. After ratings enrichment and a non-empty filtered recommendation list exists, persist the merged map into the interactive session for reuse in the same view.
4. For calendar layout, iterate enriched items in order; resolve the item’s primary course string key directly in the map without variant expansion at this step.
5. When no raw pattern or parsing yields nothing, push the item to a pending list for a separate “time to be determined” section.
6. When parsing succeeds, for each day token look up a weekday index; tokens with no index are ignored; if every token is ignored, treat the course as pending.
7. When at least one token maps, append the same item once per matching weekday index into the corresponding bucket so multi-day classes appear in multiple columns.
8. Render five header labels then five body columns listing bordered cards showing course title, parsed start–end caption, and the best professor display name when present.
9. Render the pending section with a static caption explaining missing pattern or missing workbook match.
10. On each weekday card and each **Time TBD** card, offer **Remove & replace from gaps**: when activated, the host re-invokes the memory-augmented planning entrypoint with the current plan as ``previous_plan`` and a follow-up preference that names the course to drop, the vacated weekday/time caption when parsed times exist (otherwise a Time-TBD instruction), and asks for a replacement drawn from ``missing_details``; on success the stored planning result and enrichment fingerprint refresh so ratings reload.

# Error paths

- Absent workbook leaves the map empty; filtering step elsewhere may keep all recommendations; lookup always misses so every course lands pending.
- Unparseable pattern strings or missing bar symbol force pending placement.
- Day strings that contain no recognizable weekday letters after tokenization force pending placement even when a bar and times exist.
