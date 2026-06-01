import { describe, expect, it } from "vitest";
import {
  formatPlanCourseSummarySuffix,
  instructorRatingFromRecommended,
  mergeCatalogSectionIntoPlanRow,
  mergeSlotSuggestionIntoPlanRow,
  reasonFromRecommended,
  recommendedCourseAriaSummary,
} from "../../web/src/lib/recommendedCourseDisplay";
import { recommendedToCalendarBlocks } from "../../web/src/utils/planCalendar";

describe("reasonFromRecommended", () => {
  it("returns trimmed reason when present", () => {
    expect(reasonFromRecommended({ reason: "  Fills RTC 3  " })).toBe("Fills RTC 3");
  });

  it("returns undefined for empty or missing reason", () => {
    expect(reasonFromRecommended({ reason: "   " })).toBeUndefined();
    expect(reasonFromRecommended({})).toBeUndefined();
  });

  it("truncates very long reasons for safe display", () => {
    const long = "x".repeat(400);
    const out = reasonFromRecommended({ reason: long });
    expect(out).toBeDefined();
    expect(out!.length).toBeLessThan(400);
    expect(out!.endsWith("…")).toBe(true);
  });

  it("passes through literal angle brackets (chat text, not HTML)", () => {
    const suffix = formatPlanCourseSummarySuffix({
      reason: '<img src=x onerror="alert(1)">',
      units: 4,
    });
    expect(suffix).toContain("<img");
  });
});

describe("instructorRatingFromRecommended", () => {
  it("reads rating from professors list and best_professor", () => {
    const fields = instructorRatingFromRecommended({
      course: "CSEN 174",
      best_professor: "Ada Lovelace",
      professors: [
        { name: "Other", rating: 3.0, difficulty: 2.0, would_take_again: "70%" },
        { name: "Ada Lovelace", rating: 4.5, difficulty: 3.2, would_take_again: "92%" },
      ],
    });
    expect(fields?.instructor_rating).toBe(4.5);
    expect(fields?.instructor_wta_pct).toBe(92);
    expect(fields?.instructor_display).toBe("Ada Lovelace");
  });

  it("reads nested plan-v2 instructor_rating object", () => {
    const fields = instructorRatingFromRecommended({
      course: "CSEN 174",
      section: {
        instructor: "Weijia Shang",
        instructor_rating: {
          instructor: "Weijia Shang",
          rating: 4.2,
          difficulty: 3.1,
          would_take_again_pct: 88,
          source: "rmp",
        },
      },
    });
    expect(fields?.instructor_rating).toBe(4.2);
    expect(fields?.instructor_display).toBe("Weijia Shang");
  });

  it("ignores non-finite rating numbers", () => {
    const fields = instructorRatingFromRecommended({
      professors: [{ name: "X", rating: Number.NaN, difficulty: Infinity }],
    });
    expect(fields?.instructor_rating).toBeNull();
    expect(fields?.instructor_difficulty).toBeNull();
  });

  it("prefers chosen section catalog fields when present", () => {
    const fields = instructorRatingFromRecommended(
      { course: "CSEN 174", professors: [{ name: "X", rating: 1.0 }] },
      {
        section: 1,
        meeting_days: [0],
        meeting_start_min: 100,
        meeting_end_min: 200,
        instructors: ["Y"],
        instructor_rating: 4.8,
        instructor_difficulty: 2.5,
        instructor_display: "Y",
      },
    );
    expect(fields?.instructor_rating).toBe(4.8);
  });
});

describe("recommendedToCalendarBlocks metadata", () => {
  it("attaches reason and instructor rating to calendar blocks", () => {
    const { blocks } = recommendedToCalendarBlocks([
      {
        course: "CSEN 174",
        title: "Software Engineering",
        reason: "Senior design sequence",
        best_professor: "Ada Lovelace",
        professors: [{ name: "Ada Lovelace", rating: 4.5, difficulty: 3.0, would_take_again: "90%" }],
        meeting_days: [0, 2, 4],
        meeting_start_min: 300,
        meeting_end_min: 375,
      },
    ]);
    expect(blocks.length).toBeGreaterThan(0);
    expect(blocks[0]?.reason).toBe("Senior design sequence");
    expect(blocks[0]?.instructorRating?.instructor_rating).toBe(4.5);
  });

  it("attaches reason to TBD courses without times", () => {
    const { tbd } = recommendedToCalendarBlocks([
      {
        course: "PHIL 11",
        reason: "Core ethics",
        professors: [{ name: "Smith", rating: null, difficulty: null }],
      },
    ]);
    expect(tbd).toHaveLength(1);
    expect(tbd[0]?.reason).toBe("Core ethics");
  });
});

describe("mergeCatalogSectionIntoPlanRow", () => {
  it("copies catalog instructor ratings onto a plan row", () => {
    const row = mergeCatalogSectionIntoPlanRow(
      { course: "CSEN 174", reason: "Manual" },
      {
        course: "CSEN 174",
        course_section: "CSEN 174-01",
        section: 1,
        subject: "CSEN",
        number: "174",
        title: "SE",
        units: 4,
        status: null,
        enrolled_capacity: null,
        instructors: ["Ada Lovelace"],
        meeting_days: [0],
        meeting_start_min: 100,
        meeting_end_min: 200,
        meeting_pattern: null,
        location: null,
        course_tags: [],
        lab_partner: null,
        instructor_rating: 4.6,
        instructor_difficulty: 2.8,
        instructor_wta_pct: 91,
        instructor_display: "Ada Lovelace",
      },
    );
    expect(row.instructor_rating).toBe(4.6);
    expect(instructorRatingFromRecommended(row, null)?.instructor_rating).toBe(4.6);
  });
});

describe("mergeSlotSuggestionIntoPlanRow", () => {
  it("copies slot suggestion ratings onto a plan row", () => {
    const row = mergeSlotSuggestionIntoPlanRow(
      { course: "CSEN 10", reason: "Fits slot" },
      {
        course: "CSEN 10",
        title: "Intro",
        units: 4,
        instructor: "Bob",
        rating: 4.1,
        difficulty: 2.5,
        would_take_again_pct: 80,
        rationale: "Fits slot",
      },
    );
    expect(row.instructor_rating).toBe(4.1);
  });
});

describe("formatPlanCourseSummarySuffix", () => {
  it("includes reason and instructor quality in chat summary lines", () => {
    const suffix = formatPlanCourseSummarySuffix({
      reason: "Completes major tech elective",
      best_professor: "Ada Lovelace",
      professors: [{ name: "Ada Lovelace", rating: 4.5, difficulty: 3.0 }],
    });
    expect(suffix).toContain("Completes major tech elective");
    expect(suffix).toContain("4.5★ instructor quality");
  });
});

describe("recommendedCourseAriaSummary", () => {
  it("combines reason and rating for tooltips", () => {
    const text = recommendedCourseAriaSummary({
      reason: "Fills ELSJ",
      best_professor: "Ada",
      professors: [{ name: "Ada", rating: 4.0, difficulty: 2.0 }],
    });
    expect(text).toContain("Fills ELSJ");
    expect(text).toContain("4.0");
  });
});
