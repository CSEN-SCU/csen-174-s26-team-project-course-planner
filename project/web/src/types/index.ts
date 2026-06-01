/** 0 = Monday … 4 = Friday */
export type WeekdayIndex = 0 | 1 | 2 | 3 | 4;

/** Minutes from calendar start (8:00 AM) through end (10:00 PM), max 840 */
export type MinutesFromDayStart = number;

export interface ChatSession {
  id: string;
  title: string;
  dateLabel: string;
}

/** Instructor RMP fields attached from a recommended plan row (see planCalendar). */
export type CourseBlockInstructorRating = {
  instructor_rating?: number | null;
  instructor_difficulty?: number | null;
  instructor_wta_pct?: number | null;
  instructor_display?: string | null;
  instructor_rating_source?: string | null;
};

export interface CourseBlock {
  id: string;
  dayIndex: WeekdayIndex;
  /** Minutes from 8:00 AM */
  startOffsetMin: MinutesFromDayStart;
  /** Minutes from 8:00 AM */
  endOffsetMin: MinutesFromDayStart;
  code: string;
  title?: string;
  professor: string;
  /** Planner explanation (from ``recommended[].reason``). */
  reason?: string;
  /** RMP / professor-agent rating for the displayed section. */
  instructorRating?: CourseBlockInstructorRating | null;
  /** Shown when the block was placed from a calendar slot pick */
  slotAnchored?: boolean;
  /** Real catalog meeting time when slotAnchored */
  actualTimeLabel?: string;
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  text: string;
}

export const CALENDAR_START_HOUR = 8;
export const CALENDAR_END_HOUR = 22;
/** Total span in minutes (8:00 AM – 10:00 PM) */
export const CALENDAR_SPAN_MINUTES =
  (CALENDAR_END_HOUR - CALENDAR_START_HOUR) * 60;

export const WEEKDAY_LABELS = [
  "Mon",
  "Tue",
  "Wed",
  "Thu",
  "Fri",
] as const;

// ── Four-year plan types ─────────────────────────────────────────────────────

export interface PlanCourse {
  course: string;
  title: string;
  category: string;
  units: number;
  reason: string;
}

export interface QuarterPlan {
  term: string;
  courses: PlanCourse[];
  total_units: number;
}

export interface FourYearPlan {
  quarters: QuarterPlan[];
  graduation_term: string;
  total_remaining_units: number;
  advice: string;
}

export interface ParsedRow {
  requirement: string;
  status: string;
  remaining: string | number | null;
  registration: string | null;
  course_code: string | null;
  academic_period: string | null;
  units: number | string | null;
}
