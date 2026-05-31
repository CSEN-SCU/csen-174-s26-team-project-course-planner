import { describe, expect, it } from "vitest";
import { buildFourYearPlanExportRows } from "../../web/src/lib/fourYearPlanExportRows";
import { buildFourYearPlanWorkbook } from "../../web/src/lib/exportFourYearPlanExcel";
import type { FourYearPlan, ParsedRow } from "../../web/src/types";

const completedRow: ParsedRow = {
  requirement: "Core",
  status: "Satisfied",
  remaining: null,
  registration: "CSEN 10 - Intro to Programming",
  course_code: "CSEN 10",
  academic_period: "Fall 2022 Quarter",
  units: 4,
};

const inProgressRow: ParsedRow = {
  requirement: "Core",
  status: "In Progress",
  remaining: null,
  registration: "CSEN 20 - Data Structures",
  course_code: "CSEN 20",
  academic_period: "Winter 2026 Quarter",
  units: 4,
};

const samplePlan: FourYearPlan = {
  graduation_term: "Spring 2028",
  total_remaining_units: 80,
  advice: "Stay on track.",
  quarters: [
    {
      term: "Spring 2028",
      total_units: 16,
      courses: [
        {
          course: "CSEN 196",
          title: "Senior Design III",
          category: "Senior Design",
          units: 4,
          reason: "Capstone",
        },
      ],
    },
  ],
};

describe("buildFourYearPlanExportRows", () => {
  it("marks completed transcript courses as normal weight", () => {
    const rows = buildFourYearPlanExportRows([completedRow], null);
    const csen10 = rows.find((r) => r.courseCode === "CSEN 10");
    expect(csen10).toMatchObject({
      status: "Completed",
      bold: false,
      term: "Fall 2022",
    });
  });

  it("marks in-progress transcript courses as normal weight", () => {
    const rows = buildFourYearPlanExportRows([inProgressRow], null);
    const csen20 = rows.find((r) => r.courseCode === "CSEN 20");
    expect(csen20).toMatchObject({
      status: "In Progress",
      bold: false,
    });
  });

  it("bolds planned future courses that are not yet taken", () => {
    const rows = buildFourYearPlanExportRows([completedRow], samplePlan);
    const planned = rows.find((r) => r.courseCode === "CSEN 196");
    expect(planned).toMatchObject({
      status: "Planned",
      bold: true,
      term: "Spring 2028",
      category: "Senior Design",
    });
  });

  it("does not duplicate a planned course that is already on the transcript", () => {
    const planWithOverlap: FourYearPlan = {
      ...samplePlan,
      quarters: [
        {
          term: "Fall 2022",
          total_units: 4,
          courses: [
            {
              course: "CSEN 10",
              title: "Intro to Programming",
              category: "Core",
              units: 4,
              reason: "Already done",
            },
          ],
        },
      ],
    };

    const rows = buildFourYearPlanExportRows([completedRow], planWithOverlap);
    expect(rows.filter((r) => r.courseCode === "CSEN 10")).toHaveLength(1);
    expect(rows.find((r) => r.courseCode === "CSEN 10")?.bold).toBe(false);
  });

  it("writes planned courses in bold in the Excel workbook", async () => {
    const workbook = await buildFourYearPlanWorkbook([completedRow], samplePlan);
    const sheet = workbook.getWorksheet("Four Year Plan");
    expect(sheet).toBeTruthy();

    let plannedRowNumber: number | null = null;
    sheet!.eachRow((row, rowNumber) => {
      if (row.getCell(3).value === "CSEN 196") plannedRowNumber = rowNumber;
    });

    expect(plannedRowNumber).not.toBeNull();
    const courseCell = sheet!.getRow(plannedRowNumber!).getCell(3);
    const titleCell = sheet!.getRow(plannedRowNumber!).getCell(4);
    expect(courseCell.font?.bold).toBe(true);
    expect(titleCell.font?.bold).toBe(true);
  });
});
