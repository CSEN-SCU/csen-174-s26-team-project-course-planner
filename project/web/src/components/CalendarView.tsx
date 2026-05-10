import { useMemo, useState } from "react";
import type { CourseBlock, WeekdayIndex } from "../types";
import {
  CALENDAR_END_HOUR,
  CALENDAR_SPAN_MINUTES,
  CALENDAR_START_HOUR,
  WEEKDAY_LABELS,
} from "../types";
import { recommendedToCalendarBlocks } from "../utils/planCalendar";

const SLOT_MINUTES = 30;
const SLOT_COUNT = CALENDAR_SPAN_MINUTES / SLOT_MINUTES;
const SLOT_HEIGHT_PX = 28;

const MOCK_COURSES: CourseBlock[] = [
  {
    id: "c1",
    dayIndex: 0,
    startOffsetMin: 120,
    endOffsetMin: 210,
    code: "CSEN 174",
    professor: "Dr. Nguyen",
  },
  {
    id: "c2",
    dayIndex: 0,
    startOffsetMin: 300,
    endOffsetMin: 360,
    code: "COEN 210",
    professor: "Dr. Patel",
  },
  {
    id: "c3",
    dayIndex: 2,
    startOffsetMin: 180,
    endOffsetMin: 270,
    code: "MATH 53",
    professor: "Dr. Chen",
  },
  {
    id: "c4",
    dayIndex: 3,
    startOffsetMin: 240,
    endOffsetMin: 330,
    code: "PHYS 33",
    professor: "Dr. Ortiz",
  },
  {
    id: "c5",
    dayIndex: 4,
    startOffsetMin: 90,
    endOffsetMin: 150,
    code: "CTW 1",
    professor: "Prof. Brooks",
  },
];

function startOfWeekMonday(d: Date): Date {
  const c = new Date(d);
  const day = c.getDay();
  const diff = day === 0 ? -6 : 1 - day;
  c.setDate(c.getDate() + diff);
  c.setHours(0, 0, 0, 0);
  return c;
}

function addDays(d: Date, n: number): Date {
  const x = new Date(d);
  x.setDate(x.getDate() + n);
  return x;
}

function formatWeekRangeLabel(weekStartMonday: Date): string {
  const fri = addDays(weekStartMonday, 4);
  const opts: Intl.DateTimeFormatOptions = {
    month: "short",
    day: "numeric",
    year: "numeric",
  };
  const startStr = weekStartMonday.toLocaleDateString("en-US", opts);
  const endStr = fri.toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
  return `${startStr} – ${endStr}`;
}

function formatTimeLabel(hour: number, minute: number): string {
  const d = new Date();
  d.setHours(hour, minute, 0, 0);
  return d.toLocaleTimeString("en-US", {
    hour: "numeric",
    minute: "2-digit",
    hour12: true,
  });
}

function slotOverlapsCourse(
  dayIndex: WeekdayIndex,
  slotIndex: number,
  courses: CourseBlock[],
): boolean {
  const slotStart = slotIndex * SLOT_MINUTES;
  const slotEnd = slotStart + SLOT_MINUTES;
  return courses.some(
    (c) =>
      c.dayIndex === dayIndex &&
      c.startOffsetMin < slotEnd &&
      c.endOffsetMin > slotStart,
  );
}

function formatCourseTime(startMin: number, endMin: number): string {
  const baseHour = CALENDAR_START_HOUR;
  const s = baseHour * 60 + startMin;
  const e = baseHour * 60 + endMin;
  const sh = Math.floor(s / 60);
  const sm = s % 60;
  const eh = Math.floor(e / 60);
  const em = e % 60;
  return `${formatTimeLabel(sh, sm)} – ${formatTimeLabel(eh, em)}`;
}

export type CalendarViewProps = {
  /** When non-empty, replaces placeholder mock courses (no meeting times in API). */
  recommendedCourses: Record<string, unknown>[] | null;
};

export function CalendarView({ recommendedCourses }: CalendarViewProps) {
  const [weekStart, setWeekStart] = useState(() =>
    startOfWeekMonday(new Date()),
  );

  const activeCourses = useMemo(() => {
    if (recommendedCourses && recommendedCourses.length > 0) {
      return recommendedToCalendarBlocks(recommendedCourses);
    }
    return MOCK_COURSES;
  }, [recommendedCourses]);

  const weekLabel = useMemo(() => formatWeekRangeLabel(weekStart), [weekStart]);

  const timeLabels = useMemo(() => {
    const labels: string[] = [];
    for (let i = 0; i < SLOT_COUNT; i++) {
      const totalMin = CALENDAR_START_HOUR * 60 + i * SLOT_MINUTES;
      const h = Math.floor(totalMin / 60);
      const m = totalMin % 60;
      labels.push(m === 0 ? formatTimeLabel(h, 0) : "");
    }
    return labels;
  }, []);

  const handlePrevWeek = () => {
    setWeekStart((w) => addDays(w, -7));
  };

  const handleNextWeek = () => {
    setWeekStart((w) => addDays(w, 7));
  };

  const handleEmptySlot = (day: WeekdayIndex, slotIndex: number) => {
    const dayName = WEEKDAY_LABELS[day];
    const slotStartMin = slotIndex * SLOT_MINUTES;
    console.info("Empty slot", {
      dayName,
      slotStartMin,
      weekStart: weekStart.toISOString(),
    });
  };

  const columnHeight = SLOT_COUNT * SLOT_HEIGHT_PX;

  return (
    <main className="flex min-w-0 flex-1 flex-col bg-[#F5F5F5]">
      <header className="flex shrink-0 items-center justify-between border-b border-neutral-200 bg-white px-4 py-3 shadow-sm">
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={handlePrevWeek}
            className="rounded-md p-2 text-neutral-600 hover:bg-neutral-100"
            aria-label="Previous week"
          >
            <ChevronLeftIcon />
          </button>
          <button
            type="button"
            onClick={handleNextWeek}
            className="rounded-md p-2 text-neutral-600 hover:bg-neutral-100"
            aria-label="Next week"
          >
            <ChevronRightIcon />
          </button>
        </div>
        <h1 className="text-sm font-semibold text-[var(--scu-text)]">
          {weekLabel}
        </h1>
        <div className="w-[72px]" aria-hidden />
      </header>

      <div className="min-h-0 flex-1 overflow-auto p-3">
        <div className="min-w-[720px] rounded-lg border border-neutral-200 bg-white shadow-sm">
          <div className="flex border-b border-neutral-200 bg-neutral-50">
            <div
              className="w-14 shrink-0 border-r border-neutral-200"
              aria-hidden
            />
            {WEEKDAY_LABELS.map((d) => (
              <div
                key={d}
                className="min-w-0 flex-1 border-r border-neutral-200 py-2 text-center text-xs font-semibold uppercase tracking-wide text-neutral-600 last:border-r-0"
              >
                {d}
              </div>
            ))}
          </div>

          <div className="flex">
            <div
              className="w-14 shrink-0 border-r border-neutral-200 bg-neutral-50"
              style={{ height: columnHeight }}
            >
              {timeLabels.map((label, i) => (
                <div
                  key={i}
                  className="flex justify-end pr-2 text-[10px] leading-none text-neutral-400"
                  style={{ height: SLOT_HEIGHT_PX, paddingTop: 2 }}
                >
                  {label}
                </div>
              ))}
            </div>

            {([0, 1, 2, 3, 4] as const).map((dayIndex) => (
              <div
                key={dayIndex}
                className="relative min-w-0 flex-1 border-r border-neutral-200 last:border-r-0"
                style={{ height: columnHeight }}
              >
                {Array.from({ length: SLOT_COUNT }, (_, slotIndex) => {
                  const empty = !slotOverlapsCourse(
                    dayIndex,
                    slotIndex,
                    activeCourses,
                  );
                  return (
                    <button
                      key={slotIndex}
                      type="button"
                      disabled={!empty}
                      onClick={() =>
                        empty && handleEmptySlot(dayIndex, slotIndex)
                      }
                      className={`group flex w-full items-start justify-center border-b border-neutral-100 text-neutral-400 transition ${
                        empty
                          ? "cursor-pointer hover:bg-red-50/60"
                          : "cursor-default"
                      }`}
                      style={{ height: SLOT_HEIGHT_PX }}
                    >
                      {empty ? (
                        <span className="select-none text-lg font-light opacity-0 transition group-hover:opacity-100">
                          +
                        </span>
                      ) : null}
                    </button>
                  );
                })}

                {activeCourses.filter((c) => c.dayIndex === dayIndex).map(
                  (c) => {
                    const topPct = (c.startOffsetMin / CALENDAR_SPAN_MINUTES) * 100;
                    const heightPct =
                      ((c.endOffsetMin - c.startOffsetMin) /
                        CALENDAR_SPAN_MINUTES) *
                      100;
                    return (
                      <div
                        key={c.id}
                        className="pointer-events-none absolute left-1 right-1 z-10 overflow-hidden rounded-md bg-[var(--scu-red)] px-2 py-1 text-left text-white shadow-md ring-1 ring-black/10"
                        style={{
                          top: `${topPct}%`,
                          height: `${heightPct}%`,
                          minHeight: 36,
                        }}
                      >
                        <p className="text-xs font-bold leading-tight">{c.code}</p>
                        <p className="truncate text-[10px] leading-tight opacity-95">
                          {c.professor}
                        </p>
                        <p className="mt-0.5 text-[9px] leading-tight opacity-90">
                          {formatCourseTime(c.startOffsetMin, c.endOffsetMin)}
                        </p>
                      </div>
                    );
                  },
                )}
              </div>
            ))}
          </div>
        </div>
        <p className="mt-2 text-center text-[10px] text-neutral-400">
          Showing {CALENDAR_START_HOUR}:00–{CALENDAR_END_HOUR}:00 (placeholder
          data)
        </p>
      </div>
    </main>
  );
}

function ChevronLeftIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" aria-hidden>
      <path
        d="M15 6L9 12L15 18"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function ChevronRightIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" aria-hidden>
      <path
        d="M9 6L15 12L9 18"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}
