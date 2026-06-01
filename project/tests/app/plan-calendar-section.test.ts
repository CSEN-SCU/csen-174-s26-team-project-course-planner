import { describe, expect, it } from "vitest";
import { chosenSectionNumber, recommendedToCalendarBlocks } from "../../web/src/utils/planCalendar";

describe("recommendedToCalendarBlocks backend section choice", () => {
  it("honors _chosen_section when all_sections lists multiple options", () => {
    const recs = [
      {
        course: "CSEN 174",
        title: "Software Engineering",
        _chosen_section: 2,
        meeting_days: [0, 2, 4],
        meeting_start_min: 300,
        meeting_end_min: 375,
        all_sections: [
          {
            section: 1,
            meeting_days: [0, 2, 4],
            meeting_start_min: 150,
            meeting_end_min: 225,
            instructors: ["Early"],
          },
          {
            section: 2,
            meeting_days: [0, 2, 4],
            meeting_start_min: 300,
            meeting_end_min: 375,
            instructors: ["Late"],
          },
        ],
      },
    ];

    const { blocks } = recommendedToCalendarBlocks(recs);
    expect(blocks.length).toBeGreaterThan(0);
    expect(blocks.every((b) => b.startOffsetMin === 300)).toBe(true);
    expect(blocks.some((b) => b.startOffsetMin === 150)).toBe(false);
    expect(blocks[0]?.professor).toBe("Late");
  });

  it("reads section number from section.section_number", () => {
    expect(
      chosenSectionNumber({
        section: { section_number: 3 },
      }),
    ).toBe(3);
  });
});
