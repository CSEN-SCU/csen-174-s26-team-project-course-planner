import type { ScheduledItem } from "../types/domain";
import { cn } from "../lib/ui";

export type WeeklyBlock = ScheduledItem & { isConflict: boolean };

const dayColumns = [
  { label: "Mon", code: "M" },
  { label: "Tue", code: "T" },
  { label: "Wed", code: "W" },
  { label: "Thu", code: "R" },
  { label: "Fri", code: "F" }
] as const;

const hourSlots = Array.from({ length: 13 }, (_, index) => 8 + index); // 8 AM to 8 PM

function parseHour(timeRange: string, part: "start" | "end") {
  const [start = "09:00", end = "10:00"] = timeRange.split("-");
  const target = part === "start" ? start : end;
  const [hourText] = target.split(":");
  return Number(hourText);
}

function formatHour(hour24: number) {
  const suffix = hour24 >= 12 ? "PM" : "AM";
  const hour12 = hour24 % 12 === 0 ? 12 : hour24 % 12;
  return `${hour12}:00 ${suffix}`;
}

function formatTimeRangeAmPm(timeRange: string) {
  const [start = "09:00", end = "10:00"] = timeRange.split("-");
  const format = (value: string) => {
    const [hText = "9", mText = "00"] = value.split(":");
    const hour24 = Number(hText);
    const suffix = hour24 >= 12 ? "PM" : "AM";
    const hour12 = hour24 % 12 === 0 ? 12 : hour24 % 12;
    return `${hour12}:${mText} ${suffix}`;
  };
  return `${format(start)} - ${format(end)}`;
}

export function CalendarTab({
  weeklyBlocks,
  onExportIcs,
  onExportGoogle
}: {
  weeklyBlocks: WeeklyBlock[];
  onExportIcs: () => void;
  onExportGoogle: () => void;
}) {
  return (
    <div className="grid gap-4 lg:grid-cols-[1fr_1.5fr]">
      <article className="glass rounded-2xl p-4">
        <h3 className="text-lg text-white">Current schedule</h3>
        <div className="mt-3 space-y-2">
          {weeklyBlocks.length === 0 && <p className="text-sm text-slate-300">No courses added yet.</p>}
          {weeklyBlocks.map((item) => (
            <div
              key={`${item.courseId}-${item.sectionId}`}
              className={cn(
                "rounded-lg border px-3 py-2 text-sm",
                item.isConflict ? "border-rose-500 bg-rose-950/30" : "border-slate-700 bg-slate-900/30"
              )}
            >
              <p className="font-semibold text-slate-100">
                {item.courseCode} · {item.days} {formatTimeRangeAmPm(item.time)}
              </p>
              <p className="text-xs text-slate-300">{item.instructor}</p>
              {item.conflictWith && <p className="mt-1 text-xs text-rose-300">Conflict: {item.conflictWith}</p>}
            </div>
          ))}
        </div>
        <div className="mt-4 grid gap-2">
          <button onClick={onExportIcs} className="rounded-lg bg-sky-300 px-3 py-2 text-sm font-semibold text-slate-900">
            Export schedule (.ics fallback)
          </button>
          <button onClick={onExportGoogle} className="rounded-lg border border-slate-500 px-3 py-2 text-sm text-slate-200">
            Export to Google Calendar
          </button>
        </div>
      </article>
      <article className="glass rounded-2xl p-4">
        <h3 className="text-lg text-white">Weekly calendar</h3>
        <div className="mt-3 overflow-auto">
          <div className="grid min-w-[760px] grid-cols-[120px_repeat(5,minmax(120px,1fr))] text-xs">
            <div className="border-b border-slate-700 px-2 py-2 font-semibold text-slate-300">Time</div>
            {dayColumns.map((day) => (
              <div key={day.label} className="border-b border-l border-slate-700 px-2 py-2 text-center font-semibold text-slate-200">
                {day.label}
              </div>
            ))}

            {hourSlots.map((hour) => (
              <div key={`row-${hour}`} className="contents">
                <div className="border-b border-slate-800 px-2 py-3 text-slate-300">
                  {formatHour(hour)}
                </div>
                {dayColumns.map((day) => {
                  const matching = weeklyBlocks.filter((item) => {
                    if (!item.days.includes(day.code)) return false;
                    const startHour = parseHour(item.time, "start");
                    return hour === startHour;
                  });

                  return (
                    <div key={`${day.label}-${hour}`} className="border-b border-l border-slate-800 px-1 py-1">
                      <div className="space-y-1">
                        {matching.map((item) => (
                          <div
                            key={`${day.label}-${hour}-${item.courseId}-${item.sectionId}`}
                            className={cn(
                              "rounded-md px-2 py-1",
                              item.isConflict ? "bg-rose-500/30 text-rose-100" : "bg-sky-400/20 text-sky-100"
                            )}
                          >
                            <p className="font-semibold">{item.courseCode}</p>
                            <p>{formatTimeRangeAmPm(item.time)}</p>
                          </div>
                        ))}
                      </div>
                    </div>
                  );
                })}
              </div>
            ))}
          </div>
          <p className="mt-2 text-[11px] text-slate-400">Full-day view: 8:00 AM to 8:00 PM</p>
        </div>
      </article>
    </div>
  );
}

