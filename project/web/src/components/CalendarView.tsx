import { useMemo } from "react";
import type { CourseBlock } from "../types";
import {
  CALENDAR_SPAN_MINUTES,
  CALENDAR_START_HOUR,
  WEEKDAY_LABELS,
} from "../types";
import { recommendedToCalendarBlocks } from "../utils/planCalendar";

const SLOT_MINUTES = 30;
const SLOT_COUNT = CALENDAR_SPAN_MINUTES / SLOT_MINUTES;
const SLOT_HEIGHT_PX = 28;

function formatTimeLabel(hour: number, minute: number): string {
  const d = new Date();
  d.setHours(hour, minute, 0, 0);
  return d.toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit", hour12: true });
}

function formatCourseTime(startMin: number, endMin: number): string {
  const base = CALENDAR_START_HOUR * 60;
  const sh = Math.floor((base + startMin) / 60);
  const sm = (base + startMin) % 60;
  const eh = Math.floor((base + endMin) / 60);
  const em = (base + endMin) % 60;
  return `${formatTimeLabel(sh, sm)} – ${formatTimeLabel(eh, em)}`;
}

export type CalendarViewProps = {
  recommendedCourses: Record<string, unknown>[] | null;
  onRemoveCourse?: (idx: number) => void;
  onSlotClick?: (dayIndex: number, slotIndex: number) => void;
};

export function CalendarView({ recommendedCourses, onRemoveCourse, onSlotClick }: CalendarViewProps) {

  const activeCourses = useMemo<CourseBlock[]>(() => {
    if (recommendedCourses && recommendedCourses.length > 0) {
      return recommendedToCalendarBlocks(recommendedCourses);
    }
    return [];
  }, [recommendedCourses]);

  const timeLabels = useMemo(() => {
    const labels: string[] = [];
    for (let i = 0; i < SLOT_COUNT; i++) {
      const totalMin = CALENDAR_START_HOUR * 60 + i * SLOT_MINUTES;
      labels.push(totalMin % 60 === 0 ? formatTimeLabel(Math.floor(totalMin / 60), 0) : "");
    }
    return labels;
  }, []);

  const columnHeight = SLOT_COUNT * SLOT_HEIGHT_PX;

  function extractIndex(blockId: string): number {
    return parseInt(blockId.split("-")[1] ?? "0", 10);
  }

  const isEmpty = activeCourses.length === 0;

  return (
    <main className="flex min-w-0 flex-1 flex-col bg-[#F5F5F5]">
      <header className="flex shrink-0 items-center border-b border-neutral-200 bg-white px-4 py-3 shadow-sm">
        <h1 className="text-sm font-semibold text-[var(--scu-text)]">Recommended Course Schedule</h1>
      </header>

      <div className="min-h-0 flex-1 overflow-auto p-3">
        <div className="relative min-w-[720px] rounded-lg border border-neutral-200 bg-white shadow-sm">
          {/* Empty state overlay */}
          {isEmpty && (
            <div className="absolute inset-0 z-20 flex flex-col items-center justify-center rounded-lg bg-white/90">
              <p className="text-sm font-medium text-neutral-400">No schedule yet</p>
              <p className="mt-1 text-xs text-neutral-300">
                {onSlotClick ? "Chat to generate a plan, or click any time slot to ask the AI for a course." : "Chat to generate a plan."}
              </p>
            </div>
          )}

          {/* Day headers */}
          <div className="flex border-b border-neutral-200 bg-neutral-50">
            <div className="w-14 shrink-0 border-r border-neutral-200" aria-hidden />
            {WEEKDAY_LABELS.map((d) => (
              <div
                key={d}
                className="min-w-0 flex-1 border-r border-neutral-200 py-2 text-center text-xs font-semibold uppercase tracking-wide text-neutral-600 last:border-r-0"
              >
                {d}
              </div>
            ))}
          </div>

          {/* Time grid */}
          <div className="flex">
            {/* Time labels column */}
            <div className="w-14 shrink-0 border-r border-neutral-200 bg-neutral-50" style={{ height: columnHeight }}>
              {timeLabels.map((label, i) => (
                <div key={i} className="flex justify-end pr-2 text-[10px] leading-none text-neutral-400" style={{ height: SLOT_HEIGHT_PX, paddingTop: 2 }}>
                  {label}
                </div>
              ))}
            </div>

            {/* Day columns */}
            {([0, 1, 2, 3, 4] as const).map((dayIndex) => (
              <div
                key={dayIndex}
                className="relative min-w-0 flex-1 border-r border-neutral-200 last:border-r-0"
                style={{ height: columnHeight }}
              >
                {/* Slot grid lines + click-to-suggest */}
                {Array.from({ length: SLOT_COUNT }, (_, slotIndex) => (
                  <div
                    key={slotIndex}
                    className={`group w-full border-b border-neutral-100 transition ${onSlotClick ? "hover:bg-red-50/50 cursor-pointer" : ""}`}
                    style={{ height: SLOT_HEIGHT_PX }}
                    onClick={() => onSlotClick?.(dayIndex, slotIndex)}
                  >
                    {onSlotClick && (
                      <span className="block text-center text-lg font-light text-neutral-300 opacity-0 group-hover:opacity-100 leading-none select-none" style={{ paddingTop: 4 }}>+</span>
                    )}
                  </div>
                ))}

                {/* Course blocks */}
                {activeCourses.filter((c) => c.dayIndex === dayIndex).map((c) => {
                  const topPct = (c.startOffsetMin / CALENDAR_SPAN_MINUTES) * 100;
                  const heightPct = ((c.endOffsetMin - c.startOffsetMin) / CALENDAR_SPAN_MINUTES) * 100;
                  const idx = extractIndex(c.id);
                  return (
                    <div
                      key={c.id}
                      className="absolute left-1 right-1 z-10 overflow-hidden rounded-md bg-[var(--scu-red)] px-2 py-1 text-left text-white shadow-md ring-1 ring-black/10"
                      style={{ top: `${topPct}%`, height: `${heightPct}%`, minHeight: 36 }}
                    >
                      <p className="text-xs font-bold leading-tight pr-4">{c.code}</p>
                      {c.title && <p className="truncate text-[10px] leading-tight opacity-90 font-medium">{c.title}</p>}
                      <p className="truncate text-[10px] leading-tight opacity-80">{c.professor}</p>
                      <p className="mt-0.5 text-[9px] leading-tight opacity-90">{formatCourseTime(c.startOffsetMin, c.endOffsetMin)}</p>
                      {onRemoveCourse && (
                        <button
                          type="button"
                          onClick={(e) => { e.stopPropagation(); onRemoveCourse(idx); }}
                          className="absolute right-1 top-1 rounded p-0.5 text-white/70 hover:text-white hover:bg-black/20 transition"
                          aria-label={`Remove ${c.code}`}
                        >
                          <XIcon />
                        </button>
                      )}
                    </div>
                  );
                })}

              </div>
            ))}
          </div>
        </div>
      </div>
    </main>
  );
}

function XIcon() {
  return (
    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" aria-hidden>
      <path d="M18 6L6 18M6 6l12 12" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" />
    </svg>
  );
}
