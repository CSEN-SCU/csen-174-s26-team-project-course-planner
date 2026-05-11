import type { CourseBlock, WeekdayIndex } from "../types";
import { CALENDAR_SPAN_MINUTES } from "../types";

const SLOT_MINUTES = 30;

function hashStr(s: string): number {
  let h = 0;
  for (let i = 0; i < s.length; i++) {
    h = (Math.imul(31, h) + s.charCodeAt(i)) | 0;
  }
  return Math.abs(h);
}

function professorLabel(item: Record<string, unknown>): string {
  const bp = item.best_professor;
  if (typeof bp === "string" && bp.trim()) return bp.trim();
  const si = item.scheduled_instructors;
  if (Array.isArray(si) && si.length > 0 && typeof si[0] === "string") {
    return si[0];
  }
  const profs = item.professors;
  if (Array.isArray(profs) && profs[0] && typeof profs[0] === "object") {
    const n = (profs[0] as { name?: string }).name;
    if (typeof n === "string" && n.trim()) return n.trim();
  }
  return "TBA";
}

export type ScheduleSection = {
  section: number;
  meeting_days: number[];
  meeting_start_min: number | null;
  meeting_end_min: number | null;
  instructors: string[];
};

export type TbdCourse = {
  id: string;
  code: string;
  title?: string;
  professor: string;
  index: number;
  /** Present when the course has no section with a posted time. */
  allSections?: ScheduleSection[];
};

export type CalendarResult = {
  blocks: CourseBlock[];
  tbd: TbdCourse[];
};

/**
 * Convert backend recommended items into calendar blocks.
 *
 * - Courses with a single confirmed section → placed directly on the grid.
 * - Courses with multiple sections → best non-conflicting section is auto-picked
 *   and placed on the grid. TBD panel is NOT shown for these.
 * - Courses with NO section time data → surfaced in TBD panel only.
 */
export function recommendedToCalendarBlocks(
  recs: Record<string, unknown>[],
): CalendarResult {
  const occupied: Array<Array<[number, number]>> = [[], [], [], [], []];

  function overlaps(day: number, start: number, end: number): boolean {
    return occupied[day].some(([s, e]) => start < e && end > s);
  }

  function claim(day: number, start: number, end: number) {
    occupied[day].push([start, end]);
  }

  /** Pick the first non-conflicting section; fall back to first valid one. */
  function pickBestSection(sections: ScheduleSection[]): ScheduleSection | null {
    const valid = sections.filter(
      (s) =>
        s.meeting_days.length > 0 &&
        typeof s.meeting_start_min === "number" &&
        typeof s.meeting_end_min === "number" &&
        (s.meeting_start_min as number) < (s.meeting_end_min as number),
    );
    if (valid.length === 0) return null;
    // Prefer a section that doesn't conflict with anything already claimed
    for (const sec of valid) {
      const start = sec.meeting_start_min as number;
      const end = sec.meeting_end_min as number;
      if (!sec.meeting_days.some((d) => overlaps(d, start, end))) return sec;
    }
    return valid[0]; // all conflict — still place section 1
  }

  const blocks: CourseBlock[] = [];
  const tbd: TbdCourse[] = [];

  recs.forEach((item, i) => {
    const code = String(item.course ?? "?");
    const idBase = `rec-${i}-${code.replace(/\s+/g, "-")}`;
    const title =
      typeof item.title === "string" && item.title.trim()
        ? item.title.trim()
        : undefined;
    const professor = professorLabel(item);

    // Manually placed course (user clicked a slot)
    if (
      item._manual === true &&
      typeof item._day === "number" &&
      typeof item._start === "number"
    ) {
      const units = Number(item.units) || 4;
      const durationMin = Math.min(12, Math.max(2, Math.round(units) * 2)) * SLOT_MINUTES;
      const startMin = item._start as number;
      const endMin = Math.min(startMin + durationMin, CALENDAR_SPAN_MINUTES);
      claim(item._day as number, startMin, endMin);
      blocks.push({
        id: idBase,
        dayIndex: (item._day as number) as WeekdayIndex,
        startOffsetMin: startMin,
        endOffsetMin: endMin,
        code,
        title,
        professor,
      });
      return;
    }

    const allSections = Array.isArray(item.all_sections)
      ? (item.all_sections as ScheduleSection[])
      : undefined;

    // --- Path A: all_sections data present ---
    // Auto-pick the best non-conflicting section and place it on the calendar.
    // Only goes to TBD if every section is missing a posted time.
    if (allSections && allSections.length > 0) {
      const chosen = pickBestSection(allSections);
      if (chosen) {
        const start = chosen.meeting_start_min as number;
        const end = chosen.meeting_end_min as number;
        chosen.meeting_days.forEach((dayIdx) => {
          claim(dayIdx, start, end);
          blocks.push({
            id: `${idBase}-d${dayIdx}`,
            dayIndex: dayIdx as WeekdayIndex,
            startOffsetMin: start,
            endOffsetMin: end,
            code,
            title,
            professor,
          });
        });
      } else {
        // All sections have no posted time — send to TBD
        tbd.push({ id: idBase, code, title, professor, index: i, allSections });
      }
      return;
    }

    // --- Path B: single confirmed meeting time (no sections index) ---
    const meetingDays = item.meeting_days;
    const meetingStart = item.meeting_start_min;
    const meetingEnd = item.meeting_end_min;
    if (
      Array.isArray(meetingDays) &&
      meetingDays.length > 0 &&
      typeof meetingStart === "number" &&
      typeof meetingEnd === "number" &&
      meetingStart < meetingEnd
    ) {
      meetingDays.forEach((dayIdx: number) => {
        claim(dayIdx, meetingStart, meetingEnd);
        blocks.push({
          id: `${idBase}-d${dayIdx}`,
          dayIndex: dayIdx as WeekdayIndex,
          startOffsetMin: meetingStart,
          endOffsetMin: meetingEnd,
          code,
          title,
          professor,
        });
      });
      return;
    }

    // --- Path C: no time data at all — TBD ---
    tbd.push({ id: idBase, code, title, professor, index: i });

    void hashStr; // suppress dead-code lint (used in removed hash-based path)
  });

  return { blocks, tbd };
}

export function parseRecommendedFromMemoryContent(
  content: string,
): Record<string, unknown>[] | null {
  try {
    const o = JSON.parse(content) as { recommended?: unknown };
    if (o && Array.isArray(o.recommended) && o.recommended.length > 0) {
      return o.recommended as Record<string, unknown>[];
    }
  } catch {
    /* not JSON */
  }
  return null;
}
