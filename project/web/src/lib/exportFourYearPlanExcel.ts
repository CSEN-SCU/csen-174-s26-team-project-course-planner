import ExcelJS from "exceljs";
import type { FourYearPlan, ParsedRow } from "../types";
import { buildFourYearPlanExportRows } from "./fourYearPlanExportRows";

const HEADERS = [
  "Academic Year",
  "Term",
  "Course",
  "Title",
  "Units",
  "Category",
  "Status",
] as const;

function applyBoldToCourseCells(row: ExcelJS.Row, bold: boolean) {
  if (!bold) return;
  // Columns 3 (Course) and 4 (Title) — highlight future planned courses.
  for (const col of [3, 4]) {
    const cell = row.getCell(col);
    cell.font = { ...(cell.font ?? {}), bold: true };
  }
}

export async function buildFourYearPlanWorkbook(
  parsedRows: ParsedRow[],
  plan: FourYearPlan | null,
): Promise<ExcelJS.Workbook> {
  const exportRows = buildFourYearPlanExportRows(parsedRows, plan);
  const workbook = new ExcelJS.Workbook();
  workbook.creator = "SCU Course Planner";
  const sheet = workbook.addWorksheet("Four Year Plan");

  sheet.mergeCells("A1:G1");
  const titleCell = sheet.getCell("A1");
  titleCell.value = "SCU Four-Year Plan";
  titleCell.font = { bold: true, size: 14 };

  if (plan?.graduation_term) {
    sheet.mergeCells("A2:G2");
    const gradCell = sheet.getCell("A2");
    gradCell.value = `Target graduation: ${plan.graduation_term}`;
    gradCell.font = { italic: true, size: 11 };
  }

  const headerRowNumber = plan ? 4 : 3;
  const headerRow = sheet.getRow(headerRowNumber);
  HEADERS.forEach((label, index) => {
    const cell = headerRow.getCell(index + 1);
    cell.value = label;
    cell.font = { bold: true };
    cell.fill = {
      type: "pattern",
      pattern: "solid",
      fgColor: { argb: "FFF5F5F5" },
    };
    cell.border = {
      bottom: { style: "thin", color: { argb: "FFD4D4D4" } },
    };
  });

  let rowNumber = headerRowNumber + 1;
  for (const entry of exportRows) {
    const row = sheet.getRow(rowNumber);
    row.values = [
      entry.academicYear,
      entry.term,
      entry.courseCode,
      entry.title,
      entry.units,
      entry.category,
      entry.status,
    ];
    applyBoldToCourseCells(row, entry.bold);
    rowNumber += 1;
  }

  sheet.columns = [
    { width: 14 },
    { width: 14 },
    { width: 12 },
    { width: 36 },
    { width: 8 },
    { width: 22 },
    { width: 14 },
  ];

  sheet.views = [{ state: "frozen", ySplit: headerRowNumber }];

  return workbook;
}

export async function downloadFourYearPlanExcel(
  parsedRows: ParsedRow[],
  plan: FourYearPlan | null,
): Promise<void> {
  const workbook = await buildFourYearPlanWorkbook(parsedRows, plan);
  const buffer = await workbook.xlsx.writeBuffer();
  const blob = new Blob([buffer], {
    type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
  });

  const stamp = new Date().toISOString().slice(0, 10);
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `Four_Year_Plan_${stamp}.xlsx`;
  link.click();
  URL.revokeObjectURL(url);
}
