/** 0 = Monday … 4 = Friday */
export type WeekdayIndex = 0 | 1 | 2 | 3 | 4;

/** Minutes from calendar start (8:00 AM) through end (6:00 PM), max 600 */
export type MinutesFromDayStart = number;

export interface ChatSession {
  id: string;
  title: string;
  dateLabel: string;
}

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
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  text: string;
}

export const CALENDAR_START_HOUR = 8;
export const CALENDAR_END_HOUR = 18;
/** Total span in minutes (8:00–18:00 = 10 hours) */
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
