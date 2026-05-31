import React from "react";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { CalendarView } from "../../web/src/components/CalendarView";

describe("CalendarView TBD courses", () => {
  it("opens course actions from the X button without removing immediately", async () => {
    const user = userEvent.setup();
    const onCourseClick = vi.fn();
    const onRemoveCourse = vi.fn();

    render(
      <CalendarView
        recommendedCourses={[
          {
            course: "CSEN 999",
            title: "Unscheduled Seminar",
            best_professor: "TBA",
          },
        ]}
        onCourseClick={onCourseClick}
        onRemoveCourse={onRemoveCourse}
      />,
    );

    await user.click(screen.getByRole("button", { name: "Remove CSEN 999" }));

    expect(onCourseClick).toHaveBeenCalledWith(0, "CSEN 999", expect.any(Number), expect.any(Number));
    expect(onRemoveCourse).not.toHaveBeenCalled();
  });
});
