import React from "react";
import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi, beforeEach } from "vitest";
import { Root } from "../../web/src/Root";
import { DataDisclosureContent } from "../../web/src/components/DataDisclosureContent";

vi.mock("../../web/src/api/client", () => ({
  getMemory: vi.fn(async () => ({ memories: [] })),
  saveMemory: vi.fn(async () => ({ id: 1 })),
  deleteMemory: vi.fn(async () => {}),
  deleteAllUserData: vi.fn(async () => {}),
  generateFourYearPlan: vi.fn(async () => ({ plan: null })),
  listCourses: vi.fn(async () => []),
  googleSignInUrl: vi.fn(() => ""),
  listMajors: vi.fn(async () => ({ majors: [] })),
  confirmStudentMajor: vi.fn(async () => ({})),
}));

vi.mock("../../web/src/auth/session", () => ({
  clearLocalSession: vi.fn(),
}));

// The delete-user-data query-param handler lives in <Root>, which derives the
// logged-in user from useAuth. Stub it so Root renders the authenticated shell.
vi.mock("../../web/src/hooks/useAuth", () => ({
  useAuth: () => ({
    userId: "test-user",
    googleAuthError: null,
    googleAuthPending: false,
    signOut: vi.fn(),
  }),
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

vi.mock("../../web/src/components/SiteFooter", () => ({
  SiteFooter: () => null,
}));

describe("data disclosure delete link", () => {
  beforeEach(() => {
    window.history.replaceState({}, "", "/");
    localStorage.setItem("scu_planner_intro_seen:test-user", "true");
  });

  it("renders Delete User Data as a link when the user is logged in", () => {
    render(<DataDisclosureContent showDeleteDataLink />);

    expect(screen.getByRole("link", { name: /delete user data/i }))
      .toHaveAttribute("href", "/?delete-user-data=1");
  });

  it("keeps Delete User Data as plain text when the user is logged out", () => {
    render(<DataDisclosureContent />);

    expect(screen.queryByRole("link", { name: /delete user data/i })).not.toBeInTheDocument();
    expect(screen.getByText(/delete user data/i)).toBeInTheDocument();
  });

  it("opens the delete dialog when the delete-user-data query param is present", async () => {
    window.history.replaceState({}, "", "/?delete-user-data=1");

    render(<Root />);

    expect(await screen.findByRole("alertdialog", { name: /delete user data/i }))
      .toBeInTheDocument();

    await waitFor(() => {
      expect(window.location.search).toBe("");
    });
  });
});
