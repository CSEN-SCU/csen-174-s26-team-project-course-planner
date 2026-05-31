import type { ParsedRow, QuarterPlan } from "../types";

export interface CompletedCourse {
  code: string;
  title: string;
  units: number;
}

export interface CompletedByTerm {
  [termKey: string]: CompletedCourse[];
}

export type Season = "Fall" | "Winter" | "Spring";

export interface UnifiedQuarter {
  termKey: string;
  season: Season;
  calYear: number;
  isPast: boolean;
  completedCourses: CompletedCourse[];
  plannedQuarter: QuarterPlan | null;
}

export interface UnifiedYear {
  label: string;
  acYear: number;
  quarters: UnifiedQuarter[];
}

const SEASON_ORDER: Record<Season, number> = { Fall: 0, Winter: 1, Spring: 2 };

function parseTermKey(period: string): string | null {
  const p = period.trim();
  const cap = (s: string) => s.charAt(0).toUpperCase() + s.slice(1).toLowerCase();

  const m0 = p.match(/^(Fall|Winter|Spring)\s+(\d{4})\s+Quarter$/i);
  if (m0) return `${cap(m0[1])} ${m0[2]}`;

  const m1 = p.match(/^(\d{4})-(\d{4})\s+(Fall|Winter|Spring)\s+Quarter$/i);
  if (m1) {
    const season = cap(m1[3]);
    const startYear = parseInt(m1[1], 10);
    const calYear = season === "Fall" ? startYear : startYear + 1;
    return `${season} ${calYear}`;
  }

  const m2 = p.match(/^(Fall|Winter|Spring)\s+(\d{4})-\d{4}$/i);
  if (m2) return `${cap(m2[1])} ${m2[2]}`;

  const m3 = p.match(/^(Fall|Winter|Spring)\s+(\d{4})$/i);
  if (m3) return `${cap(m3[1])} ${m3[2]}`;

  return null;
}

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

export function currentTermKey(): string {
  const now = new Date();
  const month = now.getMonth() + 1;
  const year = now.getFullYear();
  if (month >= 9) return `Fall ${year}`;
  if (month <= 3) return `Winter ${year}`;
  if (month <= 6) return `Spring ${year}`;
  return `Fall ${year}`;
}

export function buildCompletedByTerm(rows: ParsedRow[]): CompletedByTerm {
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

    if (!result[termKey]) result[termKey] = [];
    result[termKey].push({ code: row.course_code, title, units });
  }

  return result;
}

export function buildUnifiedTimeline(
  completedByTerm: CompletedByTerm,
  planQuarters: QuarterPlan[],
): UnifiedYear[] {
  const todayKey = currentTermKey();
  const todaySortKey = termSortKey(todayKey);

  const allKeys = new Set<string>([
    ...Object.keys(completedByTerm),
    ...planQuarters.map((q) => q.term),
  ]);

  const acYears = new Set<number>();
  for (const k of allKeys) {
    const ay = acYearFromTermKey(k);
    if (ay != null) acYears.add(ay);
  }
  if (acYears.size === 0) return [];

  const minAcYear = Math.min(...acYears);
  const maxAcYear = Math.max(...acYears);

  const planByTerm = new Map<string, QuarterPlan>();
  for (const q of planQuarters) planByTerm.set(q.term, q);

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
