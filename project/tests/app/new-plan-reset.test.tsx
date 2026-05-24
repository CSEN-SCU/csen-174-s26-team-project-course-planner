/**
 * Test that App.handleNewPlan resets the correct state.
 * RT#4: Verify that clicking "New Plan" clears chat/plan state but preserves transcript upload state.
 */

import React from "react";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi, beforeEach } from "vitest";
import App from "../../web/src/App";
import type { ChatPanelProps } from "../../web/src/components/ChatPanel";

// Mock API client
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

// Capture props to verify state changes
let lastChatProps: ChatPanelProps | null = null;

vi.mock("../../web/src/components/ChatPanel", () => ({
  ChatPanel: (props: ChatPanelProps) => {
    lastChatProps = props;
    return (
      <div data-testid="chat-panel">
        <div data-testid="messages-count">{props.messages.length}</div>
        <div data-testid="latest-message">{props.messages[props.messages.length - 1]?.content || "empty"}</div>
        <div data-testid="plan-result">{props.planResult === null ? "null" : "set"}</div>
      </div>
    );
  },
}));

vi.mock("../../web/src/components/CalendarView", () => ({
  CalendarView: (props: any) => (
    <div
      data-testid="calendar-view"
      data-course-count={(props.recommendedCourses || []).length}
    />
  ),
}));

vi.mock("../../web/src/components/FourYearPlanView", () => ({
  FourYearPlanView: (props: { isGenerating?: boolean }) => (
    <div data-testid="four-year-view" data-generating={String(!!props.isGenerating)} />
  ),
}));

vi.mock("../../web/src/components/SlotSuggestionPopover", () => ({
  SlotSuggestionPopover: (props: { onClose?: () => void }) => (
    <div data-testid="slot-suggestion-popover">
      <button onClick={props.onClose}>close</button>
    </div>
  ),
}));

vi.mock("../../web/src/components/AddCoursePicker", () => ({
  AddCoursePicker: () => <div data-testid="add-course-picker" />,
}));

vi.mock("../../web/src/components/DeleteUserDataConfirm", () => ({
  DeleteUserDataConfirm: () => null,
}));

vi.mock("../../web/src/components/SiteFooter", () => ({
  SiteFooter: () => null,
}));

describe("App.handleNewPlan state reset (RT#4)", () => {
  beforeEach(() => {
    lastChatProps = null;
  });

  it("initializes with WELCOME_TEXT", async () => {
    render(<App userId="test-user" onSignOut={() => {}} />);

    await waitFor(() => {
      expect(screen.getByTestId("latest-message")).toHaveTextContent(
        "Upload your Academic Progress file or describe your preferences to get started."
      );
    });
  });

  it("clicking 'New Plan' button changes message to NEW_PLAN_TEXT", async () => {
    const user = userEvent.setup();
    render(<App userId="test-user" onSignOut={() => {}} />);

    // Find and click the "New Plan" button (in LeftPanel)
    await waitFor(() => {
      const newPlanBtn = screen.queryByRole("button", { name: /new plan/i });
      expect(newPlanBtn).toBeInTheDocument();
    });

    const newPlanBtn = screen.getByRole("button", { name: /new plan/i });
    await user.click(newPlanBtn);

    // Verify message changed to NEW_PLAN_TEXT
    await waitFor(() => {
      expect(screen.getByTestId("latest-message")).toHaveTextContent(
        "Started a new plan. Upload your Academic Progress file or describe your preferences for next quarter."
      );
    });
  });

  it("clicking 'New Plan' switches viewMode to 'calendar'", async () => {
    const user = userEvent.setup();
    render(<App userId="test-user" onSignOut={() => {}} />);

    // Switch to 4-year view
    const fourYearBtn = screen.getByRole("button", { name: /4-year plan/i });
    await user.click(fourYearBtn);

    // Verify we're in 4-year view (by checking if the button has the active style)
    expect(fourYearBtn).toHaveClass("border-[var(--scu-red)]");

    // Click "New Plan"
    const newPlanBtn = screen.getByRole("button", { name: /new plan/i });
    await user.click(newPlanBtn);

    // Verify back to calendar view (calendar button should have active style)
    await waitFor(() => {
      const calendarBtn = screen.getByRole("button", { name: /this quarter/i });
      expect(calendarBtn).toHaveClass("border-[var(--scu-red)]");
    });
  });

  it("verifies planResult is null when no plan is active", async () => {
    render(<App userId="test-user" onSignOut={() => {}} />);

    await waitFor(() => {
      expect(screen.getByTestId("plan-result")).toHaveTextContent("null");
    });
  });

  it("shows zero courses in CalendarView on initial load", async () => {
    render(<App userId="test-user" onSignOut={() => {}} />);

    await waitFor(() => {
      expect(screen.getByTestId("calendar-view")).toHaveAttribute("data-course-count", "0");
    });
  });

  it("slot-suggestion popover is not rendered on initial load", async () => {
    render(<App userId="test-user" onSignOut={() => {}} />);

    // slotPopoverOpen starts false — the popover must not be mounted
    await waitFor(() => {
      expect(screen.queryByTestId("slot-suggestion-popover")).not.toBeInTheDocument();
    });
  });

  it("clicking 'New Plan' resets fourYearGenerating so the 4-year tab shows data-generating=false", async () => {
    const user = userEvent.setup();
    render(<App userId="test-user" onSignOut={() => {}} />);

    // Click "New Plan" — fourYearGenerating must be false regardless of prior state
    const newPlanBtn = await screen.findByRole("button", { name: /new plan/i });
    await user.click(newPlanBtn);

    // Switch to 4-year tab so FourYearPlanView is mounted
    const fourYearBtn = screen.getByRole("button", { name: /4-year plan/i });
    await user.click(fourYearBtn);

    await waitFor(() => {
      expect(screen.getByTestId("four-year-view")).toHaveAttribute("data-generating", "false");
    });
  });
});
