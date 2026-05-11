import type { FourYearPlan, PlanCourse, QuarterPlan } from "../types";

export type FourYearPlanViewProps = {
  plan: FourYearPlan | null;
  isGenerating: boolean;
  hasTranscript: boolean;
  onGenerate: () => void;
};

// ── Category color chips ──────────────────────────────────────────────────────

function categoryChipClass(category: string): string {
  const c = category.toLowerCase();
  if (c.includes("senior") || c.includes("design") || c.includes("capstone"))
    return "bg-orange-100 text-orange-800 border-orange-200";
  if (c.includes("core") || c.includes("required") || c.includes("major"))
    return "bg-red-100 text-red-800 border-red-200";
  if (c.includes("math") || c.includes("science") || c.includes("phys") || c.includes("chem"))
    return "bg-purple-100 text-purple-800 border-purple-200";
  if (c.includes("ge") || c.includes("general") || c.includes("elective"))
    return "bg-blue-100 text-blue-800 border-blue-200";
  if (c.includes("ethics") || c.includes("civic") || c.includes("social") || c.includes("religion") || c.includes("rsoc"))
    return "bg-teal-100 text-teal-800 border-teal-200";
  return "bg-gray-100 text-gray-700 border-gray-200";
}

function unitsBadgeClass(units: number): string {
  if (units >= 4) return "bg-[var(--scu-red)] text-white";
  return "bg-neutral-200 text-neutral-700";
}

// ── Group quarters into academic years ───────────────────────────────────────

type YearGroup = { label: string; quarters: QuarterPlan[] };

function groupByYear(quarters: QuarterPlan[]): YearGroup[] {
  const years: YearGroup[] = [];
  let currentGroup: YearGroup | null = null;
  let yearNum = 1;

  for (const q of quarters) {
    const isFall = q.term.startsWith("Fall");
    if (isFall || currentGroup === null) {
      if (currentGroup !== null) yearNum++;
      currentGroup = { label: `Year ${yearNum}`, quarters: [] };
      years.push(currentGroup);
    }
    currentGroup.quarters.push(q);
  }
  return years;
}

// ── Quarter card ─────────────────────────────────────────────────────────────

function CourseRow({ course }: { course: PlanCourse }) {
  return (
    <div className="flex items-start gap-2 py-1.5 border-b border-neutral-100 last:border-0">
      <span className={`mt-0.5 shrink-0 rounded px-1.5 py-0.5 text-[9px] font-bold border ${unitsBadgeClass(course.units)}`}>
        {course.units}u
      </span>
      <div className="min-w-0 flex-1">
        <p className="text-[11px] font-semibold text-[var(--scu-text)] leading-tight">{course.course}</p>
        {course.title && (
          <p className="truncate text-[10px] text-neutral-500 leading-tight">{course.title}</p>
        )}
        <span className={`mt-0.5 inline-block rounded-full px-1.5 py-px text-[9px] font-medium border ${categoryChipClass(course.category)}`}>
          {course.category}
        </span>
      </div>
    </div>
  );
}

function QuarterCard({ quarter }: { quarter: QuarterPlan }) {
  const [season] = quarter.term.split(" ");
  const seasonColor: Record<string, string> = {
    Fall: "bg-amber-50 border-amber-200",
    Winter: "bg-sky-50 border-sky-200",
    Spring: "bg-green-50 border-green-200",
  };
  const headerColor: Record<string, string> = {
    Fall: "bg-amber-100 text-amber-900",
    Winter: "bg-sky-100 text-sky-900",
    Spring: "bg-green-100 text-green-900",
  };

  return (
    <div className={`rounded-lg border shadow-sm overflow-hidden ${seasonColor[season] ?? "bg-white border-neutral-200"}`}>
      <div className={`px-3 py-2 flex items-center justify-between ${headerColor[season] ?? "bg-neutral-100 text-neutral-800"}`}>
        <span className="text-xs font-bold">{quarter.term}</span>
        <span className="text-[10px] font-semibold opacity-80">{quarter.total_units} units</span>
      </div>
      <div className="px-3 py-2 bg-white">
        {quarter.courses.length === 0 ? (
          <p className="text-[10px] text-neutral-400 italic">No courses scheduled</p>
        ) : (
          quarter.courses.map((c) => <CourseRow key={c.course} course={c} />)
        )}
      </div>
    </div>
  );
}

// ── Year section ─────────────────────────────────────────────────────────────

function YearSection({ group }: { group: YearGroup }) {
  const yearUnits = group.quarters.reduce((s, q) => s + q.total_units, 0);
  return (
    <section>
      <div className="flex items-center gap-3 mb-2">
        <h2 className="text-xs font-bold text-neutral-500 uppercase tracking-widest">{group.label}</h2>
        <span className="text-[10px] text-neutral-400">{yearUnits} units</span>
        <div className="flex-1 border-t border-neutral-200" />
      </div>
      <div className="grid grid-cols-3 gap-3">
        {group.quarters.map((q) => (
          <QuarterCard key={q.term} quarter={q} />
        ))}
      </div>
    </section>
  );
}

// ── Summary bar ──────────────────────────────────────────────────────────────

function SummaryBar({ plan }: { plan: FourYearPlan }) {
  const totalScheduled = plan.quarters.reduce((s, q) => s + q.total_units, 0);
  return (
    <div className="flex flex-wrap items-center gap-4 rounded-lg border border-neutral-200 bg-white px-4 py-2.5 shadow-sm text-xs text-neutral-600">
      <div>
        <span className="font-semibold text-[var(--scu-text)]">Graduation: </span>
        <span className="font-bold text-[var(--scu-red)]">{plan.graduation_term}</span>
      </div>
      <div className="h-4 w-px bg-neutral-200" />
      <div>
        <span className="font-semibold text-[var(--scu-text)]">Remaining: </span>
        {plan.total_remaining_units} units across {plan.quarters.length} quarters
      </div>
      <div className="h-4 w-px bg-neutral-200" />
      <div>
        <span className="font-semibold text-[var(--scu-text)]">Scheduled: </span>
        {totalScheduled} units
      </div>
      {plan.advice && (
        <>
          <div className="h-4 w-px bg-neutral-200" />
          <p className="flex-1 text-neutral-500 italic min-w-0">{plan.advice}</p>
        </>
      )}
    </div>
  );
}

// ── Main component ────────────────────────────────────────────────────────────

export function FourYearPlanView({ plan, isGenerating, hasTranscript, onGenerate }: FourYearPlanViewProps) {
  const yearGroups = plan ? groupByYear(plan.quarters) : [];

  return (
    <main className="flex min-w-0 flex-1 flex-col bg-[#F5F5F5]">
      <header className="flex shrink-0 items-center justify-between border-b border-neutral-200 bg-white px-4 py-3 shadow-sm">
        <h1 className="text-sm font-semibold text-[var(--scu-text)]">4-Year Graduation Plan</h1>
        <button
          onClick={onGenerate}
          disabled={isGenerating || !hasTranscript}
          className="flex items-center gap-1.5 rounded-md bg-[var(--scu-red)] px-3 py-1.5 text-xs font-semibold text-white shadow-sm transition hover:bg-red-700 disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {isGenerating ? (
            <>
              <SpinnerIcon />
              Generating…
            </>
          ) : plan ? (
            "Regenerate"
          ) : (
            "Generate Plan"
          )}
        </button>
      </header>

      <div className="min-h-0 flex-1 overflow-auto p-4 space-y-4">
        {/* Empty / no transcript */}
        {!hasTranscript && !plan && (
          <div className="flex flex-col items-center justify-center h-64 text-center">
            <p className="text-sm font-medium text-neutral-400">No transcript uploaded</p>
            <p className="mt-1 text-xs text-neutral-300">Upload your Academic Progress file in the chat panel, then generate your 4-year plan.</p>
          </div>
        )}

        {/* Has transcript, no plan yet */}
        {hasTranscript && !plan && !isGenerating && (
          <div className="flex flex-col items-center justify-center h-64 text-center">
            <p className="text-sm font-medium text-neutral-500">Ready to plan your graduation path</p>
            <p className="mt-1 text-xs text-neutral-400">Click "Generate Plan" to distribute all remaining requirements across quarters.</p>
            <button
              onClick={onGenerate}
              className="mt-4 rounded-md bg-[var(--scu-red)] px-5 py-2 text-sm font-semibold text-white shadow hover:bg-red-700 transition"
            >
              Generate 4-Year Plan
            </button>
          </div>
        )}

        {/* Loading */}
        {isGenerating && (
          <div className="flex flex-col items-center justify-center h-64 gap-3">
            <div className="h-8 w-8 animate-spin rounded-full border-4 border-[var(--scu-red)] border-t-transparent" />
            <p className="text-sm text-neutral-500">Building your graduation plan…</p>
            <p className="text-xs text-neutral-400">This may take 15–30 seconds</p>
          </div>
        )}

        {/* Plan */}
        {plan && !isGenerating && (
          <>
            <SummaryBar plan={plan} />
            {yearGroups.map((g) => (
              <YearSection key={g.label} group={g} />
            ))}
          </>
        )}
      </div>
    </main>
  );
}

function SpinnerIcon() {
  return (
    <svg className="h-3 w-3 animate-spin" viewBox="0 0 24 24" fill="none" aria-hidden>
      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4l3-3-3-3v4a8 8 0 00-8 8h4z" />
    </svg>
  );
}
