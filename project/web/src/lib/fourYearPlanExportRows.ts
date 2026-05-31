import type { FourYearPlan, ParsedRow } from "../types";
import {
  buildCompletedByTerm,
  buildUnifiedTimeline,
  type CompletedCourse,
} from "./fourYearPlanTimeline";

export type FourYearPlanExportStatus = "Completed" | "In Progress" | "Planned";

export interface FourYearPlanExportRow {
  academicYear: string;
  term: string;
  courseCode: string;
  title: string;
  units: number | string;
  category: string;
  status: FourYearPlanExportStatus;
  bold: boolean;
}

function normalizeCourseCode(code: string): string {
  return code.trim().toUpperCase();
}

function takenCourseCodes(rows: ParsedRow[]): Set<string> {
  const codes = new Set<string>();
  for (const row of rows) {
    const status = (row.status ?? "").trim();
    if (status !== "Satisfied" && status !== "In Progress") continue;
    const code = (row.course_code ?? "").trim();
    if (code) codes.add(normalizeCourseCode(code));
  }
  return codes;
}

function statusForCompletedCourse(
  course: CompletedCourse,
  termKey: string,
  parsedRows: ParsedRow[],
): FourYearPlanExportStatus {
  for (const row of parsedRows) {
    if ((row.course_code ?? "").trim() !== course.code) continue;
    const rowTerm = row.academic_period ? parseTermKeyFromRow(row.academic_period) : null;
    if (rowTerm !== termKey) continue;
    const status = (row.status ?? "").trim();
    if (status === "In Progress") return "In Progress";
    if (status === "Satisfied") return "Completed";
  }
  return "Completed";
}

function parseTermKeyFromRow(period: string): string | null {
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

export function buildFourYearPlanExportRows(
  parsedRows: ParsedRow[],
  plan: FourYearPlan | null,
): FourYearPlanExportRow[] {
  const completedByTerm = buildCompletedByTerm(parsedRows);
  const planQuarters = plan?.quarters ?? [];
  const unifiedYears = buildUnifiedTimeline(completedByTerm, planQuarters);
  const takenCodes = takenCourseCodes(parsedRows);
  const rows: FourYearPlanExportRow[] = [];

  const sortedYears = [...unifiedYears].sort((a, b) => a.acYear - b.acYear);

  for (const year of sortedYears) {
    for (const quarter of year.quarters) {
      const seenInTerm = new Set<string>();

      for (const course of quarter.completedCourses) {
        seenInTerm.add(normalizeCourseCode(course.code));
        rows.push({
          academicYear: year.label,
          term: quarter.termKey,
          courseCode: course.code,
          title: course.title,
          units: course.units > 0 ? course.units : "–",
          category: "",
          status: statusForCompletedCourse(course, quarter.termKey, parsedRows),
          bold: false,
        });
      }

      for (const course of quarter.plannedQuarter?.courses ?? []) {
        const code = course.course.trim();
        const normalized = normalizeCourseCode(code);
        if (seenInTerm.has(normalized) || takenCodes.has(normalized)) continue;

        seenInTerm.add(normalized);
        rows.push({
          academicYear: year.label,
          term: quarter.termKey,
          courseCode: code,
          title: course.title,
          units: course.units,
          category: course.category,
          status: "Planned",
          bold: true,
        });
      }
    }
  }

  return rows;
}
