import type { CatalogSection } from "../api/client";
import type { ScheduleSection } from "../utils/planCalendar";

export type InstructorRatingFields = Pick<
  CatalogSection,
  | "instructor_rating"
  | "instructor_difficulty"
  | "instructor_wta_pct"
  | "instructor_display"
  | "instructor_rating_source"
>;

/** Planner explanation for why this course appears in the schedule. */
export function reasonFromRecommended(item: Record<string, unknown>): string | undefined {
  const raw = item.reason;
  if (typeof raw !== "string") return undefined;
  const trimmed = raw.trim();
  return trimmed.length > 0 ? trimmed : undefined;
}

function parseWtaPct(raw: unknown): number | null {
  if (typeof raw === "number" && Number.isFinite(raw)) return raw;
  if (typeof raw === "string") {
    const m = raw.match(/(\d+(?:\.\d+)?)/);
    if (m) {
      const n = Number(m[1]);
      return Number.isFinite(n) ? n : null;
    }
  }
  return null;
}

function professorRecord(p: unknown): Record<string, unknown> | null {
  return p && typeof p === "object" && !Array.isArray(p) ? (p as Record<string, unknown>) : null;
}

function fieldsFromProfessorDict(
  p: Record<string, unknown>,
  displayOverride?: string,
): InstructorRatingFields {
  const rating = typeof p.rating === "number" ? p.rating : null;
  const difficulty = typeof p.difficulty === "number" ? p.difficulty : null;
  const name =
    (displayOverride && displayOverride.trim()) ||
    (typeof p.name === "string" && p.name.trim() ? p.name.trim() : null);
  return {
    instructor_rating: rating,
    instructor_difficulty: difficulty,
    instructor_wta_pct: parseWtaPct(p.would_take_again),
    instructor_display: name,
    instructor_rating_source: "rmp",
  };
}

function fieldsFromRatingRecord(ir: Record<string, unknown>): InstructorRatingFields {
  const display =
    (typeof ir.instructor === "string" && ir.instructor.trim()) ||
    (typeof ir.name === "string" && ir.name.trim()) ||
    null;
  return {
    instructor_rating: typeof ir.rating === "number" ? ir.rating : null,
    instructor_difficulty: typeof ir.difficulty === "number" ? ir.difficulty : null,
    instructor_wta_pct: parseWtaPct(ir.would_take_again_pct ?? ir.would_take_again),
    instructor_display: display,
    instructor_rating_source:
      typeof ir.source === "string" && ir.source.trim() ? ir.source.trim() : "rmp",
  };
}

function sectionRatingFields(sec: Record<string, unknown>): InstructorRatingFields | null {
  const ir = sec.instructor_rating;
  if (ir && typeof ir === "object" && !Array.isArray(ir)) {
    const base = fieldsFromRatingRecord(ir as Record<string, unknown>);
    if (!base.instructor_display && typeof sec.instructor === "string") {
      base.instructor_display = sec.instructor.trim();
    }
    if (base.instructor_rating != null || base.instructor_difficulty != null) {
      return base;
    }
  }
  if (typeof sec.instructor_rating === "number") {
    const instructors = sec.instructors;
    const lead =
      Array.isArray(instructors) && typeof instructors[0] === "string"
        ? instructors[0].trim()
        : typeof sec.instructor === "string"
          ? sec.instructor.trim()
          : null;
    return {
      instructor_rating: sec.instructor_rating,
      instructor_difficulty:
        typeof sec.instructor_difficulty === "number" ? sec.instructor_difficulty : null,
      instructor_wta_pct:
        typeof sec.instructor_wta_pct === "number" ? sec.instructor_wta_pct : null,
      instructor_display:
        (typeof sec.instructor_display === "string" && sec.instructor_display.trim()) ||
        lead ||
        null,
      instructor_rating_source:
        typeof sec.instructor_rating_source === "string"
          ? sec.instructor_rating_source
          : "rmp",
    };
  }
  return null;
}

function pickProfessorEntry(item: Record<string, unknown>): Record<string, unknown> | null {
  const profs = item.professors;
  if (!Array.isArray(profs) || profs.length === 0) return null;
  const dicts = profs.map(professorRecord).filter((p): p is Record<string, unknown> => p != null);
  if (dicts.length === 0) return null;

  const bestName =
    typeof item.best_professor === "string" ? item.best_professor.trim() : "";
  if (bestName) {
    const match = dicts.find((p) => String(p.name ?? "").trim() === bestName);
    if (match) return match;
  }

  return dicts.reduce((best, p) => {
    const br = typeof best.rating === "number" ? best.rating : -1;
    const pr = typeof p.rating === "number" ? p.rating : -1;
    return pr > br ? p : best;
  }, dicts[0]);
}

/**
 * Resolve instructor rating fields for a recommended course row.
 * Prefers the displayed section, then plan-v2 ``section`` payload, then
 * ``professors`` / ``best_professor`` from the professor agent.
 */
export function instructorRatingFromRecommended(
  item: Record<string, unknown>,
  chosenSection?: ScheduleSection | Record<string, unknown> | null,
): InstructorRatingFields | null {
  if (chosenSection && typeof chosenSection === "object") {
    const fromSec = sectionRatingFields(chosenSection as Record<string, unknown>);
    if (fromSec) return fromSec;
  }

  const nested = item.section;
  if (nested && typeof nested === "object" && !Array.isArray(nested)) {
    const fromNested = sectionRatingFields(nested as Record<string, unknown>);
    if (fromNested) return fromNested;
  }

  const prof = pickProfessorEntry(item);
  if (prof) {
    const bestName =
      typeof item.best_professor === "string" ? item.best_professor.trim() : undefined;
    const fields = fieldsFromProfessorDict(prof, bestName);
    if (
      fields.instructor_rating != null ||
      fields.instructor_difficulty != null ||
      fields.instructor_display
    ) {
      return fields;
    }
  }

  return null;
}

export function shouldShowInstructorRating(fields: InstructorRatingFields | null): boolean {
  if (!fields) return false;
  return (
    fields.instructor_rating != null ||
    fields.instructor_difficulty != null ||
    !!fields.instructor_display
  );
}

/** Tooltip / aria text combining reason and instructor summary. */
/** Suffix for chat plan summary lines: `` — reason · rating``. */
export function formatPlanCourseSummarySuffix(item: Record<string, unknown>): string {
  const reason = reasonFromRecommended(item);
  const rating = instructorRatingFromRecommended(item, null);
  const bits: string[] = [];
  if (reason) bits.push(reason);
  if (rating?.instructor_rating != null) {
    bits.push(`${rating.instructor_rating.toFixed(1)}★ instructor quality`);
  } else if (rating?.instructor_display) {
    bits.push(rating.instructor_display);
  }
  return bits.length > 0 ? ` — ${bits.join(" · ")}` : "";
}

export function recommendedCourseAriaSummary(
  item: Record<string, unknown>,
  chosenSection?: ScheduleSection | null,
): string {
  const parts: string[] = [];
  const reason = reasonFromRecommended(item);
  if (reason) parts.push(reason);
  const rating = instructorRatingFromRecommended(item, chosenSection);
  if (rating?.instructor_rating != null) {
    parts.push(`Instructor rating ${rating.instructor_rating.toFixed(1)}`);
  }
  if (rating?.instructor_display) {
    parts.push(rating.instructor_display);
  }
  return parts.join(" · ");
}
