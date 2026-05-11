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

/**
 * Backend recommended items do not include meeting times; place blocks on the
 * grid deterministically with collision detection so no two courses overlap on
 * the same day.
 */
export function recommendedToCalendarBlocks(
  recs: Record<string, unknown>[],
): CourseBlock[] {
  // Track occupied [startMin, endMin) ranges per day
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
    // Try preferred day from preferred start, then fall through to other days
    for (let d = 0; d < 5; d++) {
      const day = (preferredDay + d) % 5;
      // On fallback days start from 8:30 AM (slot 1) to avoid 8:00 AM pile-up
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
    // Last resort (calendar completely full — should never happen in practice)
    return { dayIndex: 4, startMin: 0 };
  }

  return recs.map((item, i) => {
    const code = String(item.course ?? "?");
    const units = Number(item.units) || 4;
    const durationSlots = Math.min(12, Math.max(2, Math.round(units) * 2));
    const durationMin = durationSlots * SLOT_MINUTES;
    const id = `rec-${i}-${code.replace(/\s+/g, "-")}`;
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
      return {
        id,
        dayIndex: (item._day as number) as WeekdayIndex,
        startOffsetMin: startMin,
        endOffsetMin: endMin,
        code,
        title,
        professor,
      };
    }

    // Hash-based preferred position with collision avoidance
    const h = hashStr(`${code}:${i}`);
    const preferredDay = h % 5;
    const preferredStart = (2 + (h % 12)) * SLOT_MINUTES; // 9:00 AM – 2:30 PM range

    const { dayIndex, startMin } = findFreeSlot(preferredDay, preferredStart, durationMin);
    const endMin = Math.min(startMin + durationMin, CALENDAR_SPAN_MINUTES);
    claim(dayIndex, startMin, endMin);

    return { id, dayIndex, startOffsetMin: startMin, endOffsetMin: endMin, code, title, professor };
  });
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
