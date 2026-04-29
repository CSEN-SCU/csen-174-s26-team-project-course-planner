import React from "react";
import { fireEvent, render, screen } from "@testing-library/react";
import { PlannerNav } from "../web/src/components/PlannerNav";

describe("PlannerNav", () => {
  it("changes tabs and priority mode through user interactions", () => {
    // As a student, I can switch planner tabs and choose a priority mode so I can build a schedule my way.
    // Arrange
    const onTabChange = vi.fn();
    const onPriorityModeChange = vi.fn();

    render(
      <PlannerNav
        activeTab="build"
        onTabChange={onTabChange}
        priorityMode="balanced"
        onPriorityModeChange={onPriorityModeChange}
      />
    );

    // Action
    fireEvent.click(screen.getByRole("button", { name: "calendar" }));
    fireEvent.change(screen.getByRole("combobox"), { target: { value: "quality" } });

    // Assert
    expect(onTabChange).toHaveBeenCalledWith("calendar");
    expect(onPriorityModeChange).toHaveBeenCalledWith("quality");
  });
});
