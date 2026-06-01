/** @vitest-environment jsdom */
import React from "react";
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { CalendarView } from "../../web/src/components/CalendarView";

describe("CalendarView explainability", () => {
  it("renders per-course reason and instructor quality on scheduled blocks", () => {
    render(
      <CalendarView
        recommendedCourses={[
          {
            course: "CSEN 174",
            title: "Software Engineering",
            units: 4,
            reason: "Completes major elective",
            best_professor: "Ada Lovelace",
            professors: [
              { name: "Ada Lovelace", rating: 4.5, difficulty: 3.0, would_take_again: "90%" },
            ],
            meeting_days: [0],
            meeting_start_min: 120,
            meeting_end_min: 195,
          },
        ]}
      />,
    );

    expect(screen.getAllByText("CSEN 174").length).toBeGreaterThan(0);
    expect(screen.getByText("Completes major elective")).toBeInTheDocument();
    expect(screen.getByText("4.5")).toBeInTheDocument();
    expect(screen.getByText(/quality/)).toBeInTheDocument();
  });

  it("renders reason on TBD courses without meeting times", () => {
    render(
      <CalendarView
        recommendedCourses={[
          {
            course: "PHIL 11",
            reason: "Core ethics requirement",
            professors: [{ name: "Smith", rating: null, difficulty: null }],
          },
        ]}
      />,
    );

    expect(screen.getByText("PHIL 11")).toBeInTheDocument();
    expect(screen.getByText("Core ethics requirement")).toBeInTheDocument();
    expect(screen.getByText(/Time not yet posted/i)).toBeInTheDocument();
  });
});
