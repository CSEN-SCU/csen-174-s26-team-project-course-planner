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

export type TbdCourse = {
  id: string;
  code: string;
  title?: string;
  professor: string;
  index: number;
};

export type CalendarResult = {
  blocks: CourseBlock[];
  tbd: TbdCourse[];
};

/**
 * Convert backend recommended items into calendar blocks.
 * Courses with real meeting times (from schedule xlsx) get one block per
 * meeting day. Courses with no schedule data are returned in `tbd` — never
 * placed at a made-up time.
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

  function findFreeSlot(
    preferredDay: number,
    preferredStart: number,
    durationMin: number,
  ): { dayIndex: WeekdayIndex; startMin: number } {
    for (let d = 0; d < 5; d++) {
      const day = (preferredDay + d) % 5;
      const scanFrom = d === 0 ? preferredStart : SLOT_MINUTES;
      for (
        let s = Math.floor(scanFrom / SLOT_MINUTES) * SLOT_MINUTES;
        s + durationMin <= CALENDAR_SPAN_MINUTES;
        s += SLOT_MINUTES
      ) {
        if (!overlaps(day, s, s + durationMin)) {
          return { dayIndex: day as WeekdayIndex, startMin: s };
        }
      }
    }
    return { dayIndex: 4, startMin: 0 };
  }

  const blocks: CourseBlock[] = [];
  const tbd: TbdCourse[] = [];

  recs.forEach((item, i) => {
    const code = String(item.course ?? "?");
    const units = Number(item.units) || 4;
    const durationSlots = Math.min(12, Math.max(2, Math.round(units) * 2));
    const durationMin = durationSlots * SLOT_MINUTES;
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

    // Real meeting times from schedule xlsx — one block per meeting day
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

    // No schedule data — do NOT make up a time; surface as TBD
    tbd.push({ id: idBase, code, title, professor, index: i });

    // Still use hash-based slot for manually-placed only — here just skip
    void findFreeSlot; // referenced to avoid dead-code lint; not used for TBD
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
