import {
  instructorRatingFromRecommended,
  reasonFromRecommended,
} from "../lib/recommendedCourseDisplay";
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

function professorLabel(
  item: Record<string, unknown>,
  chosenSection?: ScheduleSection | null,
): string {
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
  const fromSection = chosenSection?.instructors?.[0];
  if (typeof fromSection === "string" && fromSection.trim()) {
    return fromSection.trim();
  }
  return "TBA";
}

export type ScheduleSection = {
  section: number;
  meeting_days: number[];
  meeting_start_min: number | null;
  meeting_end_min: number | null;
  instructors: string[];
  instructor_display?: string | null;
  instructor_rating?: number | null;
  instructor_difficulty?: number | null;
  instructor_wta_pct?: number | null;
  instructor_rating_source?: string | null;
};

export type TbdCourse = {
  id: string;
  code: string;
  title?: string;
  professor: string;
  index: number;
  reason?: string;
  instructorRating?: CourseBlock["instructorRating"];
  /** Present when the course has no section with a posted time. */
  allSections?: ScheduleSection[];
};

export type CalendarResult = {
  blocks: CourseBlock[];
  tbd: TbdCourse[];
};

function isValidSection(s: ScheduleSection): boolean {
  return (
    s.meeting_days.length > 0 &&
    typeof s.meeting_start_min === "number" &&
    typeof s.meeting_end_min === "number" &&
    (s.meeting_start_min as number) < (s.meeting_end_min as number)
  );
}

function sameMeetingDays(a: number[], b: number[]): boolean {
  if (a.length !== b.length) return false;
  const sa = [...a].sort((x, y) => x - y);
  const sb = [...b].sort((x, y) => x - y);
  return sa.every((d, i) => d === sb[i]);
}

/** Section number stamped by the backend planner (v2 / llm_select). */
export function chosenSectionNumber(item: Record<string, unknown>): number | undefined {
  if (typeof item._chosen_section === "number") return item._chosen_section;
  if (typeof item._section === "number") return item._section;
  const sec = item.section;
  if (sec && typeof sec === "object") {
    const n = (sec as { section_number?: unknown }).section_number;
    if (typeof n === "number") return n;
  }
  return undefined;
}

function resolveBackendSection(
  item: Record<string, unknown>,
  allSections: ScheduleSection[],
): ScheduleSection | null {
  const num = chosenSectionNumber(item);
  if (num != null) {
    const match = allSections.find((s) => s.section === num);
    if (match && isValidSection(match)) return match;
  }
  const days = item.meeting_days;
  const start = item.meeting_start_min;
  const end = item.meeting_end_min;
  if (Array.isArray(days) && typeof start === "number" && typeof end === "number") {
    const match = allSections.find(
      (s) =>
        isValidSection(s) &&
        s.meeting_start_min === start &&
        s.meeting_end_min === end &&
        sameMeetingDays(s.meeting_days, days as number[]),
    );
    if (match) return match;
  }
  return null;
}

type BlockMeta = {
  reason?: string;
  instructorRating?: CourseBlock["instructorRating"];
};

function placeSectionOnCalendar(
  sec: ScheduleSection,
  idBase: string,
  code: string,
  title: string | undefined,
  professor: string,
  claim: (day: number, start: number, end: number) => void,
  blocks: CourseBlock[],
  meta: BlockMeta = {},
) {
  const start = sec.meeting_start_min as number;
  const end = sec.meeting_end_min as number;
  sec.meeting_days.forEach((dayIdx) => {
    claim(dayIdx, start, end);
    blocks.push({
      id: `${idBase}-d${dayIdx}`,
      dayIndex: dayIdx as WeekdayIndex,
      startOffsetMin: start,
      endOffsetMin: end,
      code,
      title,
      professor,
      reason: meta.reason,
      instructorRating: meta.instructorRating,
    });
  });
}

/**
 * Convert backend recommended items into calendar blocks.
 *
 * - Backend-stamped section (_chosen_section / top-level meeting times) wins
 *   over auto-picking the first non-conflicting section.
 * - Courses with multiple sections and no backend choice → first
 *   non-conflicting section.
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
    const reason = reasonFromRecommended(item);
    const allSectionsEarly = Array.isArray(item.all_sections)
      ? (item.all_sections as ScheduleSection[])
      : undefined;

    const blockMetaForChosen = (chosen: ScheduleSection | null): BlockMeta => ({
      reason,
      instructorRating: instructorRatingFromRecommended(item, chosen),
    });

    let professor = professorLabel(item);

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
        reason,
        instructorRating: instructorRatingFromRecommended(item, null),
      });
      return;
    }

    const allSections = allSectionsEarly;

    // --- Path A: all_sections data present ---
    if (allSections && allSections.length > 0) {
      const backendChosen = resolveBackendSection(item, allSections);
      const chosen = backendChosen ?? pickBestSection(allSections);
      if (chosen) {
        professor = professorLabel(item, chosen);
        placeSectionOnCalendar(
          chosen,
          idBase,
          code,
          title,
          professor,
          claim,
          blocks,
          blockMetaForChosen(chosen),
        );
      } else {
        tbd.push({
          id: idBase,
          code,
          title,
          professor,
          index: i,
          reason,
          instructorRating: instructorRatingFromRecommended(item, null),
          allSections,
        });
      }
      return;
    }

    // --- Path B0: placed from calendar slot (draw at clicked cell; show real time in UI) ---
    if (
      item._slotAnchored === true &&
      typeof item._anchoredDayIndex === "number" &&
      typeof item._anchoredStartMin === "number" &&
      typeof item._anchoredEndMin === "number"
    ) {
      const day = item._anchoredDayIndex as number;
      const start = item._anchoredStartMin as number;
      const end = item._anchoredEndMin as number;
      if (start < end && day >= 0 && day <= 4) {
        claim(day, start, end);
        blocks.push({
          id: `${idBase}-anchored-d${day}`,
          dayIndex: day as WeekdayIndex,
          startOffsetMin: start,
          endOffsetMin: end,
          code,
          title,
          professor,
          reason,
          instructorRating: instructorRatingFromRecommended(item, null),
          slotAnchored: true,
          actualTimeLabel:
            typeof item._actualTimeLabel === "string" ? item._actualTimeLabel : undefined,
        });
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
          reason,
          instructorRating: instructorRatingFromRecommended(item, null),
        });
      });
      return;
    }

    // --- Path C: no time data at all — TBD ---
    tbd.push({
      id: idBase,
      code,
      title,
      professor,
      index: i,
      reason,
      instructorRating: instructorRatingFromRecommended(item, null),
    });

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
