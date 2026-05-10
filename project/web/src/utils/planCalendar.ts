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
 * grid deterministically so the calendar reflects the current plan.
 */
export function recommendedToCalendarBlocks(
  recs: Record<string, unknown>[],
): CourseBlock[] {
  return recs.map((item, i) => {
    const code = String(item.course ?? "?");
    const h = hashStr(`${code}:${i}`);
    const dayIndex = (h % 5) as WeekdayIndex;
    const units = Number(item.units) || 4;
    const startSlot = 2 + (h % 12);
    const durationSlots = Math.min(
      12,
      Math.max(2, Math.round(units) * 2),
    );
    const startOffsetMin = startSlot * SLOT_MINUTES;
    const endOffsetMin = Math.min(
      startOffsetMin + durationSlots * SLOT_MINUTES,
      CALENDAR_SPAN_MINUTES,
    );
    return {
      id: `rec-${i}-${code.replace(/\s+/g, "-")}`,
      dayIndex,
      startOffsetMin,
      endOffsetMin: Math.max(endOffsetMin, startOffsetMin + SLOT_MINUTES * 2),
      code,
      professor: professorLabel(item),
    };
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
