import React from "react";
import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { SlotSuggestionPopover } from "../../web/src/components/SlotSuggestionPopover";
import { suggestCoursesForSlot } from "../../web/src/api/client";

vi.mock("../../web/src/api/client", () => ({
  suggestCoursesForSlot: vi.fn(),
}));

const mockedSuggest = vi.mocked(suggestCoursesForSlot);

describe("SlotSuggestionPopover", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockedSuggest.mockResolvedValue({
      candidates: [],
      count: 0,
      message: null,
      enrichment: {
        track_label: "Chinese (CHIN)",
        subjects: ["CHIN"],
        prompt: null,
        candidates: [
          {
            course: "CHIN 125",
            title: "Chinese Cinema",
            units: 5,
            instructor: "Prof",
            rating: 4.8,
            difficulty: 2.1,
            rationale: "Major enrichment",
            covers: ["Educational Enrichment", "Chinese (CHIN)"],
            kind: "enrichment",
            meeting_days: [0],
            meeting_start_min: 60,
            meeting_end_min: 110,
          },
        ],
      },
    });
  });

  it("keeps Add enabled for additional enrichment sequence courses", async () => {
    render(
      <SlotSuggestionPopover
        day_index={0}
        slot_index={0}
        start_min={60}
        end_min={110}
        missing_details={[{ requirement: "Educational Enrichment - Courses" }]}
        excluded_courses={["CHIN 1"]}
        satisfied_covers={["Educational Enrichment", "Chinese (CHIN)"]}
        user_preference="Chinese enrichment"
        onAddCourse={vi.fn()}
        onClose={vi.fn()}
        client_x={100}
        client_y={100}
      />,
    );

    expect(await screen.findByRole("button", { name: "Add" })).toBeEnabled();
  });
});
