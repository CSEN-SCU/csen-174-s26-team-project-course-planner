import type { ScheduledItem } from "../types/domain";
import { cn } from "../lib/ui";

export type WeeklyBlock = ScheduledItem & { isConflict: boolean };

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
                {item.courseCode} · {item.days} {item.time}
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
        <div className="mt-3 grid grid-cols-5 gap-2 text-xs">
          {["Mon", "Tue", "Wed", "Thu", "Fri"].map((day) => (
            <div key={day} className="rounded-lg border border-slate-700 bg-slate-900/25 p-2">
              <p className="mb-2 font-semibold text-slate-200">{day}</p>
              <div className="space-y-2">
                {weeklyBlocks
                  .filter((item) => item.days.includes(day[0]))
                  .map((item) => (
                    <div
                      key={`${day}-${item.courseId}-${item.sectionId}`}
                      className={cn(
                        "rounded-md px-2 py-1",
                        item.isConflict ? "bg-rose-500/30 text-rose-100" : "bg-sky-400/20 text-sky-100"
                      )}
                    >
                      <p>{item.courseCode}</p>
                      <p>{item.time}</p>
                    </div>
                  ))}
              </div>
            </div>
          ))}
        </div>
      </article>
    </div>
  );
}

