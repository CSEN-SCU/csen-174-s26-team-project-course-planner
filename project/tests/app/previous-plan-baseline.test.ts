import { describe, expect, it } from "vitest";
import { previousPlanFromCalendar } from "../../web/src/utils/previousPlan";

describe("previousPlanFromCalendar", () => {
  it("uses calendar-visible courses when manual edits exist", () => {
    const stale = {
      recommended: [{ course: "CSEN 10", units: 4 }],
      total_units: 4,
    };
    const effective = [
      { course: "CSEN 10", units: 4 },
      { course: "CHIN 1", units: 5, _manualAdd: true },
    ];

    const out = previousPlanFromCalendar(effective, stale);

    expect(out?.recommended).toEqual(effective);
    expect(out?.total_units).toBe(9);
  });

  it("falls back to planResult when the calendar is empty", () => {
    const stale = { recommended: [{ course: "MATH 11", units: 4 }], total_units: 4 };
    expect(previousPlanFromCalendar([], stale)).toBe(stale);
    expect(previousPlanFromCalendar([], null)).toBeNull();
  });
});
