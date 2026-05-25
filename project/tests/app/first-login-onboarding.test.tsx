import React from "react";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import App from "../../web/src/App";

vi.mock("../../web/src/api/client", () => ({
  getMemory: vi.fn(async () => ({ memories: [] })),
  saveMemory: vi.fn(async () => ({ id: 1 })),
  deleteMemory: vi.fn(async () => {}),
  deleteAllUserData: vi.fn(async () => {}),
  generateFourYearPlan: vi.fn(async () => ({ plan: null })),
  listCourses: vi.fn(async () => []),
  googleSignInUrl: vi.fn(() => ""),
}));

vi.mock("../../web/src/auth/session", () => ({
  clearLocalSession: vi.fn(),
}));

vi.mock("../../web/src/components/ChatPanel", () => ({
  ChatPanel: () => <div data-testid="chat-panel" />,
}));

vi.mock("../../web/src/components/CalendarView", () => ({
  CalendarView: () => <div data-testid="calendar-view" />,
}));

vi.mock("../../web/src/components/FourYearPlanView", () => ({
  FourYearPlanView: () => <div data-testid="four-year-view" />,
}));

vi.mock("../../web/src/components/SlotSuggestionPopover", () => ({
  SlotSuggestionPopover: () => <div data-testid="slot-suggestion-popover" />,
}));

vi.mock("../../web/src/components/AddCoursePicker", () => ({
  AddCoursePicker: () => <div data-testid="add-course-picker" />,
}));

vi.mock("../../web/src/components/DeleteUserDataConfirm", () => ({
  DeleteUserDataConfirm: () => null,
}));

describe("first-login onboarding carousel", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it("shows the intro overlay once for a new logged-in user and persists dismissal", async () => {
    const user = userEvent.setup();
    const { unmount } = render(<App userId="new-user" onSignOut={() => {}} />);

    expect(await screen.findByRole("dialog", { name: /welcome to scu course planner/i }))
      .toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /welcome to scu course planner/i }))
      .toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /next/i }));
    expect(screen.getByRole("heading", { name: /data disclosure/i })).toBeInTheDocument();
    expect(screen.getByText(/Academic Progress data/i)).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /next/i }));
    expect(screen.getByRole("heading", { name: /academic progress export/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /open academic progress export tutorial/i }))
      .toHaveAttribute("target", "_blank");

    await user.click(screen.getByRole("button", { name: /next/i }));
    expect(screen.getByRole("heading", { name: /scu course planner tutorial/i }))
      .toBeInTheDocument();
    expect(screen.getByRole("button", { name: /start/i })).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /start/i }));
    await waitFor(() => {
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    });

    unmount();
    render(<App userId="new-user" onSignOut={() => {}} />);

    await waitFor(() => {
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    });
  });

  it("shows again for a different user on the same browser", async () => {
    localStorage.setItem("scu_planner_intro_seen:first-user", "true");

    render(<App userId="second-user" onSignOut={() => {}} />);

    expect(await screen.findByRole("dialog", { name: /welcome to scu course planner/i }))
      .toBeInTheDocument();
  });

  it("shows a footer help button on the main app that reopens the carousel", async () => {
    const user = userEvent.setup();
    localStorage.setItem("scu_planner_intro_seen:returning-user", "true");

    render(<App userId="returning-user" onSignOut={() => {}} />);

    await waitFor(() => {
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    });

    await user.click(screen.getByRole("button", { name: /open help guide/i }));

    expect(await screen.findByRole("dialog", { name: /welcome to scu course planner/i }))
      .toBeInTheDocument();
  });
});
