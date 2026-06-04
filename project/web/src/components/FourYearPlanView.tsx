import type { FourYearPlan, ParsedRow, PlanCourse } from "../types";
import {
  buildCompletedByTerm,
  buildUnifiedTimeline,
  type CompletedCourse,
  type Season,
  type UnifiedQuarter,
  type UnifiedYear,
} from "../lib/fourYearPlanTimeline";
import { buildFourYearPlanExportRows } from "../lib/fourYearPlanExportRows";
import { downloadFourYearPlanExcel } from "../lib/exportFourYearPlanExcel";
import { useState } from "react";

export type FourYearPlanViewProps = {
  plan: FourYearPlan | null;
  isGenerating: boolean;
  hasTranscript: boolean;
  /** Called with the user's free-text preferences when generating/regenerating. */
  onGenerate: (preferences: string) => void;
  parsedRows: ParsedRow[];
};

// ── Category color chips ──────────────────────────────────────────────────────

function categoryChipClass(category: string): string {
  const c = category.toLowerCase();
  if (
    c.includes("engineering") ||
    c.includes("csen") ||
    c.includes("coen") ||
    c.includes("elen") ||
    c.includes("ecen")
  )
    return "bg-green-100 text-green-800 border-green-200";
  if (c.includes("core") || c.includes("required") || c.includes("major"))
    return "bg-red-100 text-red-800 border-red-200";
  if (
    c.includes("math") ||
    c.includes("science") ||
    c.includes("phys") ||
    c.includes("chem") ||
    c.includes("biol")
  )
    return "bg-purple-100 text-purple-800 border-purple-200";
  if (c.includes("ge") || c.includes("general") || c.includes("elective"))
    return "bg-sky-100 text-sky-800 border-sky-200";
  if (
    c.includes("ethics") ||
    c.includes("civic") ||
    c.includes("social") ||
    c.includes("religion") ||
    c.includes("rsoc")
  )
    return "bg-teal-100 text-teal-800 border-teal-200";
  if (
    c.includes("humanity") ||
    c.includes("humanities") ||
    c.includes("university core")
  )
    return "bg-yellow-100 text-yellow-800 border-yellow-200";
  return "bg-gray-100 text-gray-700 border-gray-200";
}

function isSeniorDesignCategory(category: string): boolean {
  const c = category.trim().toLowerCase();
  return c.includes("senior design") || c.includes("capstone");
}

const SEASON_CARD_BG: Record<Season, string> = {
  Fall: "bg-amber-50 border-amber-200",
  Winter: "bg-sky-50 border-sky-200",
  Spring: "bg-green-50 border-green-200",
};

function CompletedCourseRow({ course }: { course: CompletedCourse }) {
  return (
    <div className="flex items-start gap-2 py-1.5 border-b border-neutral-100 last:border-0">
      <span className="mt-0.5 shrink-0 rounded px-1.5 py-0.5 text-[9px] font-bold border bg-neutral-200 text-neutral-600 border-neutral-300">
        {course.units > 0 ? `${course.units}u` : "–"}
      </span>
      <div className="min-w-0 flex-1">
        <p className="text-[11px] font-semibold text-neutral-500 leading-tight">{course.code}</p>
        {course.title && (
          <p className="truncate text-[10px] text-neutral-400 leading-tight">{course.title}</p>
        )}
      </div>
    </div>
  );
}

function RecommendedCourseRow({ course }: { course: PlanCourse }) {
  const unitsBg =
    course.units >= 4 ? "bg-[var(--scu-red)] text-white" : "bg-neutral-200 text-neutral-700";
  return (
    <div className="flex items-start gap-2 py-1.5 border-b border-neutral-100 last:border-0">
      <span
        className={`mt-0.5 shrink-0 rounded px-1.5 py-0.5 text-[9px] font-bold border ${unitsBg}`}
      >
        {course.units}u
      </span>
      <div className="min-w-0 flex-1">
        <p className="text-[11px] font-semibold text-[var(--scu-text)] leading-tight">
          {course.course}
        </p>
        {course.title && (
          <p className="truncate text-[10px] text-neutral-500 leading-tight">{course.title}</p>
        )}
        {course.category && !isSeniorDesignCategory(course.category) && (
          <span
            className={`mt-0.5 inline-block rounded-full px-1.5 py-px text-[9px] font-medium border ${categoryChipClass(course.category)}`}
          >
            {course.category}
          </span>
        )}
      </div>
    </div>
  );
}

const SEASON_HEADER_BG: Record<Season, string> = {
  Fall: "bg-amber-100 text-amber-900",
  Winter: "bg-sky-100 text-sky-900",
  Spring: "bg-green-100 text-green-900",
};

function QuarterCard({ quarter }: { quarter: UnifiedQuarter }) {
  const { termKey, season, isPast, completedCourses, plannedQuarter } = quarter;

  const totalCompletedUnits = completedCourses.reduce((s, c) => s + c.units, 0);
  const totalPlannedUnits = plannedQuarter ? plannedQuarter.total_units : 0;
  // A current/future quarter can hold BOTH in-progress (enrolled) courses and
  // newly planned ones, so the quarter total must sum both — otherwise a
  // 17-unit enrolled quarter shows only the planned-course units.
  const totalUnits = isPast
    ? totalCompletedUnits
    : totalCompletedUnits + totalPlannedUnits;

  const hasAnything =
    completedCourses.length > 0 || (plannedQuarter && plannedQuarter.courses.length > 0);

  const cardBg = isPast
    ? "bg-neutral-50 border-neutral-200"
    : SEASON_CARD_BG[season];
  const headerBg = isPast
    ? "bg-neutral-100 text-neutral-500"
    : SEASON_HEADER_BG[season];

  return (
    <div className={`rounded-lg border shadow-sm overflow-hidden ${cardBg}`}>
      <div className={`px-3 py-2 flex items-center justify-between ${headerBg}`}>
        <span className="text-xs font-bold">{termKey}</span>
        {totalUnits > 0 && (
          <span className="text-[10px] font-semibold opacity-80">{totalUnits} units</span>
        )}
      </div>
      <div className="px-3 py-2 bg-white">
        {!hasAnything ? (
          <p className="text-[10px] text-neutral-300 italic py-1">—</p>
        ) : (
          <>
            {completedCourses.map((c) => (
              <CompletedCourseRow key={c.code} course={c} />
            ))}
            {plannedQuarter &&
              plannedQuarter.courses.map((c) => (
                <RecommendedCourseRow key={c.course} course={c} />
              ))}
          </>
        )}
      </div>
    </div>
  );
}

function YearSection({ year }: { year: UnifiedYear }) {
  const totalUnits = year.quarters.reduce((s, q) => {
    const completed = q.completedCourses.reduce((su, c) => su + c.units, 0);
    if (q.isPast) return s + completed;
    return s + completed + (q.plannedQuarter?.total_units ?? 0);
  }, 0);

  return (
    <section>
      <div className="flex items-center gap-3 mb-2">
        <h2 className="text-xs font-bold text-neutral-500 uppercase tracking-widest">
          {year.label}
        </h2>
        {totalUnits > 0 && (
          <span className="text-[10px] text-neutral-400">{totalUnits} units</span>
        )}
        <div className="flex-1 border-t border-neutral-200" />
      </div>
      <div className="grid grid-cols-3 gap-3">
        {year.quarters.map((q) => (
          <QuarterCard key={q.termKey} quarter={q} />
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
    </div>
  );
}

// ── Color legend ─────────────────────────────────────────────────────────────

const LEGEND_ITEMS: { label: string; chip: string }[] = [
  { label: "Completed", chip: "bg-neutral-100 text-neutral-500 border-neutral-200" },
  { label: "Major", chip: "bg-green-100 text-green-800 border-green-200" },
  { label: "Math/Science", chip: "bg-purple-100 text-purple-800 border-purple-200" },
  { label: "Core", chip: "bg-red-100 text-red-800 border-red-200" },
  { label: "Elective", chip: "bg-sky-100 text-sky-800 border-sky-200" },
];

function Legend() {
  return (
    <div className="flex flex-wrap items-center gap-2 rounded-lg border border-neutral-100 bg-white px-4 py-2 text-[10px]">
      <span className="font-semibold text-neutral-400 uppercase tracking-wide mr-1">Legend:</span>
      {LEGEND_ITEMS.map(({ label, chip }) => (
        <span
          key={label}
          className={`rounded-full border px-2 py-0.5 font-medium ${chip}`}
        >
          {label}
        </span>
      ))}
    </div>
  );
}

// ── Main component ────────────────────────────────────────────────────────────

export function FourYearPlanView({
  plan,
  isGenerating,
  hasTranscript,
  onGenerate,
  parsedRows,
}: FourYearPlanViewProps) {
  const [isExporting, setIsExporting] = useState(false);
  const completedByTerm = buildCompletedByTerm(parsedRows);
  const planQuarters = plan?.quarters ?? [];

  // Only show the timeline if we have something to show
  const hasCompletedData = Object.keys(completedByTerm).length > 0;
  const hasPlannedData = planQuarters.length > 0;
  const showTimeline = hasCompletedData || hasPlannedData;
  const exportRows = buildFourYearPlanExportRows(parsedRows, plan);
  const canExport = showTimeline && !isGenerating && exportRows.length > 0;

  const unifiedYears = showTimeline
    ? buildUnifiedTimeline(completedByTerm, planQuarters)
    : [];

  // Sort unified years by acYear
  const sortedYears = [...unifiedYears].sort((a, b) => a.acYear - b.acYear);

  const handleExport = async () => {
    if (!canExport || isExporting) return;
    setIsExporting(true);
    try {
      await downloadFourYearPlanExcel(parsedRows, plan);
    } finally {
      setIsExporting(false);
    }
  };

  return (
    <main className="flex min-h-0 min-w-0 flex-1 flex-col bg-[#F5F5F5]">
      <div className="min-h-0 flex-1 overflow-auto p-4 space-y-4">
        {/* No transcript uploaded yet */}
        {!hasTranscript && !showTimeline && (
          <div className="flex flex-col items-center justify-center h-64 text-center">
            <p className="text-sm font-medium text-neutral-400">No Academic Progress file uploaded</p>
            <p className="mt-1 text-xs text-neutral-300">
              Upload your Academic Progress file in the chat panel, then generate your Four-Year Plan.
            </p>
          </div>
        )}

        {/* Has transcript but no plan yet and not generating */}
        {hasTranscript && !plan && !isGenerating && !hasCompletedData && (
          <div className="flex flex-col items-center justify-center h-64 text-center">
            <p className="text-sm font-medium text-neutral-500">Ready to plan your graduation path</p>
            <p className="mt-1 text-xs text-neutral-400">
              Click "Generate Plan" to distribute all remaining requirements across quarters.
            </p>
            <button
              onClick={() => onGenerate("")}
              className="mt-4 rounded-md bg-[var(--scu-red)] px-5 py-2 text-sm font-semibold text-white shadow hover:bg-red-700 transition"
            >
              Generate Four-Year Plan
            </button>
          </div>
        )}

        {/* Loading spinner */}
        {isGenerating && (
          <div className="flex flex-col items-center justify-center h-64 gap-3">
            <div className="h-8 w-8 animate-spin rounded-full border-4 border-[var(--scu-red)] border-t-transparent" />
            <p className="text-sm text-neutral-500">Building your graduation plan…</p>
            <p className="text-xs text-neutral-400">This may take 15–30 seconds</p>
          </div>
        )}

        {/* Main timeline */}
        {showTimeline && !isGenerating && (
          <>
            {plan && <SummaryBar plan={plan} />}
            <Legend />

            {sortedYears.map((y) => (
              <YearSection key={y.acYear} year={y} />
            ))}

            <div className="rounded-lg border border-neutral-200 bg-white px-4 py-3">
              <div className="flex flex-col items-center gap-3">
                <button
                  type="button"
                  onClick={() => void handleExport()}
                  disabled={!canExport || isExporting}
                  className="rounded-md border border-neutral-300 bg-white px-4 py-2 text-sm font-semibold text-[var(--scu-text)] shadow-sm transition hover:bg-neutral-50 disabled:cursor-not-allowed disabled:opacity-50"
                >
                  {isExporting ? "Exporting…" : "Export to Spreadsheet"}
                </button>
                <p className="text-center text-xs italic text-neutral-500">
                  Please double check any generated Four-Year Plan with your major requiremenets and course availability. Planned courses not yet taken appear in <span className="font-bold">bold</span> in
                  the spreadsheet.
                </p>
              </div>
            </div>
          </>
        )}
      </div>
    </main>
  );
}
