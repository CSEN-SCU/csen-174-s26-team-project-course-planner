import type { FourYearPlan, ParsedRow, PlanCourse, QuarterPlan } from "../types";

export type FourYearPlanViewProps = {
  plan: FourYearPlan | null;
  isGenerating: boolean;
  hasTranscript: boolean;
  onGenerate: () => void;
  parsedRows: ParsedRow[];
};

// ── Category color chips ──────────────────────────────────────────────────────

function categoryChipClass(category: string): string {
  const c = category.toLowerCase();
  if (c.includes("senior") || c.includes("design") || c.includes("capstone"))
    return "bg-orange-100 text-orange-800 border-orange-200";
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

// ── Parse academic_period strings into a canonical "Season YYYY" key ─────────

function parseTermKey(period: string): string | null {
  const p = period.trim();
  const cap = (s: string) => s.charAt(0).toUpperCase() + s.slice(1).toLowerCase();

  // "Fall 2023 Quarter" / "Winter 2024 Quarter" / "Spring 2025 Quarter"
  // (SCU Workday's actual format — single calendar year + 'Quarter' suffix)
  const m0 = p.match(/^(Fall|Winter|Spring)\s+(\d{4})\s+Quarter$/i);
  if (m0) return `${cap(m0[1])} ${m0[2]}`;

  // "2022-2023 Fall Quarter" → "Fall 2022"
  // "2022-2023 Winter Quarter" → "Winter 2023"
  // "2022-2023 Spring Quarter" → "Spring 2023"
  const m1 = p.match(/^(\d{4})-(\d{4})\s+(Fall|Winter|Spring)\s+Quarter$/i);
  if (m1) {
    const season = cap(m1[3]);
    const startYear = parseInt(m1[1], 10);
    const calYear = season === "Fall" ? startYear : startYear + 1;
    return `${season} ${calYear}`;
  }

  // "Fall 2022-2023" → "Fall 2022"
  const m2 = p.match(/^(Fall|Winter|Spring)\s+(\d{4})-\d{4}$/i);
  if (m2) return `${cap(m2[1])} ${m2[2]}`;

  // "Fall 2022" (bare)
  const m3 = p.match(/^(Fall|Winter|Spring)\s+(\d{4})$/i);
  if (m3) return `${cap(m3[1])} ${m3[2]}`;

  return null;
}

// ── Completed course derived from ParsedRow ───────────────────────────────────

interface CompletedCourse {
  code: string;
  title: string;
  units: number;
  grade: string;
}

interface CompletedByTerm {
  [termKey: string]: CompletedCourse[];
}

function buildCompletedByTerm(rows: ParsedRow[]): CompletedByTerm {
  const result: CompletedByTerm = {};
  const seen = new Set<string>();

  for (const row of rows) {
    if (!row.course_code || !row.academic_period) continue;
    const status = (row.status ?? "").trim();
    if (status !== "Satisfied" && status !== "In Progress") continue;

    const termKey = parseTermKey(row.academic_period);
    if (!termKey) continue;

    const dedupeKey = `${termKey}||${row.course_code}`;
    if (seen.has(dedupeKey)) continue;
    seen.add(dedupeKey);

    // Parse title from registration string: "CSEN 122 - Data Structures" → "Data Structures"
    let title = "";
    if (row.registration && row.registration.includes(" - ")) {
      const parts = row.registration.split(" - ");
      title = parts.slice(1).join(" - ").trim();
    }

    let units = 0;
    if (typeof row.units === "number") {
      units = row.units;
    } else if (typeof row.units === "string") {
      const parsed = parseFloat(row.units);
      if (!isNaN(parsed)) units = parsed;
    }

    const grade =
      row.grade != null && String(row.grade).trim() !== ""
        ? String(row.grade).trim()
        : "";

    if (!result[termKey]) result[termKey] = [];
    result[termKey].push({ code: row.course_code, title, units, grade });
  }

  return result;
}

// ── Determine academic year from term key ─────────────────────────────────────
// Academic year = the Fall year.  Fall 2022 → acYear=2022.
// Winter 2023, Spring 2023 → also acYear=2022 (same academic year as Fall 2022).

type Season = "Fall" | "Winter" | "Spring";
const SEASON_ORDER: Record<Season, number> = { Fall: 0, Winter: 1, Spring: 2 };

function parseTermKeyParts(termKey: string): { season: Season; calYear: number } | null {
  const m = termKey.match(/^(Fall|Winter|Spring)\s+(\d{4})$/);
  if (!m) return null;
  return { season: m[1] as Season, calYear: parseInt(m[2], 10) };
}

function acYearFromTermKey(termKey: string): number | null {
  const parts = parseTermKeyParts(termKey);
  if (!parts) return null;
  const { season, calYear } = parts;
  return season === "Fall" ? calYear : calYear - 1;
}

function termSortKey(termKey: string): number {
  const parts = parseTermKeyParts(termKey);
  if (!parts) return 99999;
  const acYear = parts.season === "Fall" ? parts.calYear : parts.calYear - 1;
  return acYear * 3 + SEASON_ORDER[parts.season];
}

// ── Determine today's term ────────────────────────────────────────────────────

function currentTermKey(): string {
  const now = new Date();
  const month = now.getMonth() + 1; // 1-12
  const year = now.getFullYear();
  // SCU approximate: Fall=Sep-Dec, Winter=Jan-Mar, Spring=Apr-Jun, Summer=Jul-Aug
  if (month >= 9) return `Fall ${year}`;
  if (month <= 3) return `Winter ${year}`;
  if (month <= 6) return `Spring ${year}`;
  return `Fall ${year}`;
}

// ── Build unified timeline ────────────────────────────────────────────────────

interface UnifiedQuarter {
  termKey: string;
  season: Season;
  calYear: number;
  isPast: boolean;
  completedCourses: CompletedCourse[];
  plannedQuarter: QuarterPlan | null;
}

interface UnifiedYear {
  label: string;
  acYear: number;
  quarters: UnifiedQuarter[];
}

function buildUnifiedTimeline(
  completedByTerm: CompletedByTerm,
  planQuarters: QuarterPlan[],
): UnifiedYear[] {
  const todayKey = currentTermKey();
  const todaySortKey = termSortKey(todayKey);

  // Collect all term keys
  const allKeys = new Set<string>([
    ...Object.keys(completedByTerm),
    ...planQuarters.map((q) => q.term),
  ]);

  // Determine academic year range
  const acYears = new Set<number>();
  for (const k of allKeys) {
    const ay = acYearFromTermKey(k);
    if (ay != null) acYears.add(ay);
  }
  if (acYears.size === 0) return [];

  const minAcYear = Math.min(...acYears);
  const maxAcYear = Math.max(...acYears);

  // Build plan lookup
  const planByTerm = new Map<string, QuarterPlan>();
  for (const q of planQuarters) planByTerm.set(q.term, q);

  // Generate all quarters for each academic year in range
  const years: UnifiedYear[] = [];
  let yearLabel = 1;

  for (let ay = minAcYear; ay <= maxAcYear; ay++) {
    const quarters: UnifiedQuarter[] = [];
    for (const season of ["Fall", "Winter", "Spring"] as Season[]) {
      const calYear = season === "Fall" ? ay : ay + 1;
      const termKey = `${season} ${calYear}`;
      const sortKey = termSortKey(termKey);
      const parts = parseTermKeyParts(termKey);
      if (!parts) continue;

      quarters.push({
        termKey,
        season,
        calYear,
        isPast: sortKey < todaySortKey,
        completedCourses: completedByTerm[termKey] ?? [],
        plannedQuarter: planByTerm.get(termKey) ?? null,
      });
    }
    years.push({ label: `Year ${yearLabel}`, acYear: ay, quarters });
    yearLabel++;
  }

  return years;
}

// ── Sub-components ────────────────────────────────────────────────────────────

function CompletedCourseRow({ course }: { course: CompletedCourse }) {
  return (
    <div className="flex items-start gap-2 py-1.5 border-b border-neutral-100 last:border-0">
      <span className="mt-0.5 shrink-0 rounded px-1.5 py-0.5 text-[9px] font-bold border bg-neutral-200 text-neutral-600 border-neutral-300">
        {course.units > 0 ? `${course.units}u` : "–"}
      </span>
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-1.5">
          <p className="text-[11px] font-semibold text-neutral-500 leading-tight">{course.code}</p>
          {course.grade && (
            <span className="shrink-0 rounded-full bg-neutral-100 border border-neutral-200 px-1.5 py-px text-[9px] font-bold text-neutral-500">
              {course.grade}
            </span>
          )}
        </div>
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
        <span
          className={`mt-0.5 inline-block rounded-full px-1.5 py-px text-[9px] font-medium border ${categoryChipClass(course.category)}`}
        >
          {course.category}
        </span>
      </div>
    </div>
  );
}

const SEASON_CARD_BG: Record<Season, string> = {
  Fall: "bg-amber-50 border-amber-200",
  Winter: "bg-sky-50 border-sky-200",
  Spring: "bg-green-50 border-green-200",
};
const SEASON_HEADER_BG: Record<Season, string> = {
  Fall: "bg-amber-100 text-amber-900",
  Winter: "bg-sky-100 text-sky-900",
  Spring: "bg-green-100 text-green-900",
};

function QuarterCard({ quarter }: { quarter: UnifiedQuarter }) {
  const { termKey, season, isPast, completedCourses, plannedQuarter } = quarter;

  const totalCompletedUnits = completedCourses.reduce((s, c) => s + c.units, 0);
  const totalPlannedUnits = plannedQuarter ? plannedQuarter.total_units : 0;
  const totalUnits = isPast
    ? totalCompletedUnits
    : totalPlannedUnits || totalCompletedUnits;

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
              <CompletedCourseRow key={`${c.code}-${c.grade}`} course={c} />
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
    if (q.isPast) {
      return s + q.completedCourses.reduce((su, c) => su + c.units, 0);
    }
    return s + (q.plannedQuarter?.total_units ?? 0);
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
      {plan.advice && (
        <>
          <div className="h-4 w-px bg-neutral-200" />
          <p className="flex-1 text-neutral-500 italic min-w-0">{plan.advice}</p>
        </>
      )}
    </div>
  );
}

// ── Color legend ─────────────────────────────────────────────────────────────

const LEGEND_ITEMS: { label: string; chip: string }[] = [
  { label: "Completed", chip: "bg-neutral-100 text-neutral-500 border-neutral-200" },
  { label: "Senior Design", chip: "bg-orange-100 text-orange-800 border-orange-200" },
  { label: "Engineering", chip: "bg-green-100 text-green-800 border-green-200" },
  { label: "Math/Science", chip: "bg-purple-100 text-purple-800 border-purple-200" },
  { label: "Core/Humanities", chip: "bg-yellow-100 text-yellow-800 border-yellow-200" },
  { label: "Elective/GE", chip: "bg-sky-100 text-sky-800 border-sky-200" },
  { label: "Ethics", chip: "bg-teal-100 text-teal-800 border-teal-200" },
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
  const completedByTerm = buildCompletedByTerm(parsedRows);
  const planQuarters = plan?.quarters ?? [];

  // Only show the timeline if we have something to show
  const hasCompletedData = Object.keys(completedByTerm).length > 0;
  const hasPlannedData = planQuarters.length > 0;
  const showTimeline = hasCompletedData || hasPlannedData;

  const unifiedYears = showTimeline
    ? buildUnifiedTimeline(completedByTerm, planQuarters)
    : [];

  // Sort unified years by acYear
  const sortedYears = [...unifiedYears].sort((a, b) => a.acYear - b.acYear);

  return (
    <main className="flex min-h-0 min-w-0 flex-1 flex-col bg-[#F5F5F5]">
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
        {/* No transcript uploaded yet */}
        {!hasTranscript && !showTimeline && (
          <div className="flex flex-col items-center justify-center h-64 text-center">
            <p className="text-sm font-medium text-neutral-400">No transcript uploaded</p>
            <p className="mt-1 text-xs text-neutral-300">
              Upload your Academic Progress file in the chat panel, then generate your 4-year plan.
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
              onClick={onGenerate}
              className="mt-4 rounded-md bg-[var(--scu-red)] px-5 py-2 text-sm font-semibold text-white shadow hover:bg-red-700 transition"
            >
              Generate 4-Year Plan
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

            {/* Prompt to generate if we have completed data but no plan */}
            {hasCompletedData && !plan && (
              <div className="flex items-center gap-3 rounded-lg border border-dashed border-neutral-300 bg-white px-4 py-3 text-xs text-neutral-500">
                <span>Completed courses loaded from transcript.</span>
                <button
                  onClick={onGenerate}
                  className="ml-auto shrink-0 rounded-md bg-[var(--scu-red)] px-3 py-1.5 text-xs font-semibold text-white shadow-sm transition hover:bg-red-700"
                >
                  Generate Remaining Plan
                </button>
              </div>
            )}

            {sortedYears.map((y) => (
              <YearSection key={y.acYear} year={y} />
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
      <path
        className="opacity-75"
        fill="currentColor"
        d="M4 12a8 8 0 018-8v4l3-3-3-3v4a8 8 0 00-8 8h4z"
      />
    </svg>
  );
}
