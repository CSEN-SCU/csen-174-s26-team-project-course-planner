import type { CourseType, Division, Filters, TranscriptSummary } from "../types/domain";
import { cn } from "../lib/ui";

const requirementOptions = ["ELSJ", "Diversity", "Social Science", "Science with Lab", "Technical Elective"];

export function TranscriptScreen({
  summary,
  filters,
  onToggleType,
  onToggleDivision,
  onToggleRequirement,
  onTimeWindowChange,
  onContinue,
  onOpenAi,
  onOpenCalendar
}: {
  summary: TranscriptSummary;
  filters: Filters;
  onToggleType: (type: CourseType) => void;
  onToggleDivision: (division: Division) => void;
  onToggleRequirement: (req: string) => void;
  onTimeWindowChange: (next: string) => void;
  onContinue: () => void;
  onOpenAi: () => void;
  onOpenCalendar: () => void;
}) {
  return (
    <section className="grid gap-6 lg:grid-cols-[1.2fr_1fr]">
      <article className="glass rounded-2xl p-6">
        <h2 className="text-2xl text-white">Transcript summary</h2>
        <p className="mt-2 text-slate-200">
          {summary.studentName} · {summary.major} · {summary.unitsCompleted} units completed
        </p>
        <div className="mt-4 grid gap-4 md:grid-cols-2">
          <div>
            <h3 className="font-semibold text-sky-200">Completed courses</h3>
            <ul className="mt-2 space-y-1 text-sm text-slate-100">
              {summary.completedCourses.map((course) => (
                <li key={course} className="rounded bg-slate-900/50 px-2 py-1">
                  {course}
                </li>
              ))}
            </ul>
          </div>
          <div>
            <h3 className="font-semibold text-peach">Remaining requirements</h3>
            <ul className="mt-2 space-y-1 text-sm text-slate-100">
              {summary.remainingRequirements.map((requirement) => (
                <li key={requirement} className="rounded bg-slate-900/50 px-2 py-1">
                  {requirement}
                </li>
              ))}
            </ul>
          </div>
        </div>
      </article>
      <article className="glass rounded-2xl p-6">
        <h3 className="text-xl text-white">Set your filters</h3>
        <p className="mt-1 text-sm text-slate-300">Only eligible courses will be returned from the backend.</p>
        <div className="mt-4 space-y-4">
          <fieldset>
            <legend className="text-sm font-semibold text-slate-200">Type</legend>
            <div className="mt-2 flex flex-wrap gap-2">
              {(["core", "major", "elective"] as CourseType[]).map((type) => (
                <button
                  key={type}
                  onClick={() => onToggleType(type)}
                  className={cn(
                    "rounded-full border px-3 py-1 text-xs uppercase",
                    filters.types.includes(type) ? "border-sky-300 bg-sky-300/20 text-sky-100" : "border-slate-500 text-slate-200"
                  )}
                >
                  {type}
                </button>
              ))}
            </div>
          </fieldset>

          <fieldset>
            <legend className="text-sm font-semibold text-slate-200">Division</legend>
            <div className="mt-2 flex gap-2">
              {(["upper", "lower"] as Division[]).map((division) => (
                <button
                  key={division}
                  onClick={() => onToggleDivision(division)}
                  className={cn(
                    "rounded-full border px-3 py-1 text-xs uppercase",
                    filters.divisions.includes(division) ? "border-mint bg-mint/20 text-mint" : "border-slate-500 text-slate-200"
                  )}
                >
                  {division}
                </button>
              ))}
            </div>
          </fieldset>

          <fieldset>
            <legend className="text-sm font-semibold text-slate-200">Requirements</legend>
            <div className="mt-2 flex flex-wrap gap-2">
              {requirementOptions.map((req) => (
                <button
                  key={req}
                  onClick={() => onToggleRequirement(req)}
                  className={cn(
                    "rounded-full border px-3 py-1 text-xs",
                    filters.requirements.includes(req) ? "border-peach bg-peach/20 text-peach" : "border-slate-500 text-slate-200"
                  )}
                >
                  {req}
                </button>
              ))}
            </div>
          </fieldset>

          <label className="block text-sm font-semibold text-slate-200">
            Preferred time window
            <input
              value={filters.timeWindow}
              onChange={(event) => onTimeWindowChange(event.target.value)}
              className="mt-2 w-full rounded-lg border border-slate-500 bg-slate-900/40 px-3 py-2 text-sm text-slate-100"
              placeholder="Morning / Midday / Afternoon"
            />
          </label>

          <button onClick={onContinue} className="w-full rounded-xl bg-sky-300 px-4 py-3 font-semibold text-slate-900 transition hover:bg-sky-200">
            Continue to eligible courses
          </button>
          <div className="grid gap-2 sm:grid-cols-2">
            <button
              onClick={onOpenAi}
              className="rounded-xl border border-slate-500 px-4 py-3 text-sm font-semibold text-slate-100 transition hover:border-sky-300"
            >
              Go to AI chat
            </button>
            <button
              onClick={onOpenCalendar}
              className="rounded-xl border border-slate-500 px-4 py-3 text-sm font-semibold text-slate-100 transition hover:border-sky-300"
            >
              Go to calendar
            </button>
          </div>
        </div>
      </article>
    </section>
  );
}

