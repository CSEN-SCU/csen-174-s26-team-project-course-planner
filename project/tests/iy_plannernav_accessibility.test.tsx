import React from "react";
import { render, screen } from "@testing-library/react";
import { PlannerNav } from "../web/src/components/PlannerNav";

describe("PlannerNav accessibility", () => {
  it("marks the active tab for assistive technology", () => {
    // As a student using a screen reader, I can tell which planner tab is currently active.
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
    const activeTabButton = screen.getByRole("button", { name: "build" });

    // Assert
    expect(activeTabButton).toHaveAttribute("aria-current", "page");
  });
});
