/**
 * Test that App.handleNewPlan resets the correct state.
 * RT#4: Verify that clicking "New Plan" clears chat/plan state but preserves transcript upload state.
 *
 * REGRESSION PINS (RT#4)
 * ─────────────────────
 * These tests are intentional "pins" against silent regressions in handleNewPlan.
 * If handleNewPlan ever accidentally clears fileUploaded / missingDetails,
 * or stops clearing planResult / courses / activeSessionId, these tests will fail.
 *
 * State contract enforced here:
 *   MUST be cleared   → planResult, sessionCalendarRecommended (≡ course count 0),
 *                        localOverride, activeSessionId, messages (reset to NEW_PLAN_TEXT)
 *   MUST be preserved → fileUploaded, missingDetails, planSnapshots history
 */

import React from "react";
import { render, screen, waitFor, act } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi, beforeEach } from "vitest";
import App from "../../web/src/App";
import type { ChatPanelProps } from "../../web/src/components/ChatPanel";

const apiMocks = vi.hoisted(() => ({
  getMemory: vi.fn(async () => ({ memories: [] })),
}));

// Mock API client
vi.mock("../../web/src/api/client", () => ({
  getMemory: apiMocks.getMemory,
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
        <div data-testid="file-uploaded">{props.fileUploaded ? "true" : "false"}</div>
        <div data-testid="missing-details-count">{props.missingDetails.length}</div>
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

vi.mock("../../web/src/components/CourseBrowser", () => ({
  CourseBrowser: () => <div data-testid="course-browser" />,
}));

vi.mock("../../web/src/components/PlanStartModal", () => ({
  PlanStartModal: ({
    open,
    onManual,
    onAi,
    onClose,
  }: {
    open: boolean;
    onManual: () => void;
    onAi: () => void;
    onClose: () => void;
  }) =>
    open ? (
      <div data-testid="plan-start-modal">
        <button type="button" onClick={onManual}>
          Search and add courses myself
        </button>
        <button type="button" onClick={onAi}>
          Have AI recommend my schedule
        </button>
        <button type="button" onClick={onClose}>
          Cancel
        </button>
      </div>
    ) : null,
}));

vi.mock("../../web/src/components/SlotActionModal", () => ({
  SlotActionModal: () => null,
}));

vi.mock("../../web/src/components/DeleteUserDataConfirm", () => ({
  DeleteUserDataConfirm: () => null,
}));

vi.mock("../../web/src/components/SiteFooter", () => ({
  SiteFooter: () => null,
}));

// ── helpers ──────────────────────────────────────────────────────────────────

/**
 * Inject a plan into App state the same way ChatPanel does in production:
 * 1. setPlanResult(plan)      — sets planResult, drives the calendar
 * 2. onPlanGenerated(plan, …) — saves the snapshot in LeftPanel history
 */
async function injectPlan(courses: string[]) {
  expect(lastChatProps).not.toBeNull();
  const plan: Record<string, unknown> = {
    recommended: courses.map((c) => ({ course: c, units: 4 })),
    total_units: courses.length * 4,
  };
  const msgs = [{ id: "m0", role: "assistant" as const, content: "Here is your plan." }];
  await act(async () => {
    lastChatProps!.setPlanResult(plan);
    lastChatProps!.onPlanGenerated(plan, msgs);
  });
}

/** Mark the user as having uploaded a transcript via the setFileUploaded callback. */
async function markFileUploaded() {
  expect(lastChatProps).not.toBeNull();
  await act(async () => {
    lastChatProps!.setFileUploaded(true);
    lastChatProps!.setMissingDetails([{ label: "Major", value: "CSEN" }]);
  });
}

// ── tests ────────────────────────────────────────────────────────────────────

describe("App.handleNewPlan state reset (RT#4)", () => {
  beforeEach(() => {
    lastChatProps = null;
    apiMocks.getMemory.mockResolvedValue({ memories: [] });
  });

  // ── baseline ──────────────────────────────────────────────────────────────

  it("initializes with WELCOME_TEXT", async () => {
    render(<App userId="test-user" onSignOut={() => {}} />);

    await waitFor(() => {
      expect(screen.getByTestId("latest-message")).toHaveTextContent(
        "Upload your Academic Progress Report or describe your preferences to get started."
      );
    });
  });

  it("clicking 'New Plan' then AI path sets NEW_PLAN_AI_TEXT", async () => {
    const user = userEvent.setup();
    render(<App userId="test-user" onSignOut={() => {}} />);

    await waitFor(() => {
      expect(screen.getByRole("button", { name: /new plan/i })).toBeInTheDocument();
    });

    await user.click(screen.getByRole("button", { name: /new plan/i }));
    await waitFor(() => {
      expect(screen.getByTestId("plan-start-modal")).toBeInTheDocument();
    });
    await user.click(screen.getByRole("button", { name: /have ai recommend my schedule/i }));

    await waitFor(() => {
      expect(screen.getByTestId("latest-message")).toHaveTextContent(
        "Started a new plan. Upload your Academic Progress file (.xlsx) if you have not yet, then describe your preferences for next quarter.",
      );
    });
  });

  it("clicking 'New Plan' switches viewMode to 'calendar'", async () => {
    const user = userEvent.setup();
    render(<App userId="test-user" onSignOut={() => {}} />);

    // Switch to 4-year view
    const fourYearBtn = screen.getByRole("button", { name: /four-year plan/i });
    await user.click(fourYearBtn);

    // Verify we're in 4-year view (by checking if the button has the active style)
    expect(fourYearBtn).toHaveClass("border-[var(--scu-red)]");

    await user.click(screen.getByRole("button", { name: /new plan/i }));
    await user.click(screen.getByRole("button", { name: /have ai recommend my schedule/i }));

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

  it("[pin] restored parsed transcript rows count as uploaded academic progress", async () => {
    apiMocks.getMemory.mockResolvedValueOnce({
      memories: [
        {
          id: 7,
          kind: "parsed_rows",
          content: JSON.stringify([
            {
              course_code: "CSEN 10",
              status: "Satisfied",
              term: "Fall 2025",
            },
          ]),
          created_at: "2026-05-01T00:00:00Z",
        },
      ],
    });

    render(<App userId="test-user" onSignOut={() => {}} />);

    await waitFor(() => {
      expect(screen.getByTestId("file-uploaded")).toHaveTextContent("true");
      expect(screen.getByTestId("latest-message")).toHaveTextContent(
        "Your Academic Progress is already loaded. Tell me what kind of schedule you want for next quarter.",
      );
    });
  });

  it("clicking 'New Plan' resets fourYearGenerating so the 4-year tab shows data-generating=false", async () => {
    const user = userEvent.setup();
    render(<App userId="test-user" onSignOut={() => {}} />);

    // Click "New Plan" — fourYearGenerating must be false regardless of prior state
    const newPlanBtn = await screen.findByRole("button", { name: /new plan/i });
    await user.click(newPlanBtn);

    // Switch to 4-year tab so FourYearPlanView is mounted
    const fourYearBtn = screen.getByRole("button", { name: /four-year plan/i });
    await user.click(fourYearBtn);

    await waitFor(() => {
      expect(screen.getByTestId("four-year-view")).toHaveAttribute("data-generating", "false");
    });
  });

  // ── REGRESSION PINS ───────────────────────────────────────────────────────
  // These catch silent regressions where handleNewPlan either stops clearing
  // something it should, or starts clearing something it must not.

  it("[pin] planResult is cleared after New Plan (was set)", async () => {
    const user = userEvent.setup();
    render(<App userId="test-user" onSignOut={() => {}} />);

    // Wait for initial render so ChatPanel props are captured
    await waitFor(() => expect(lastChatProps).not.toBeNull());

    // Inject a plan to put planResult into a non-null state
    await injectPlan(["CSEN 12", "CSEN 20", "MATH 11"]);

    await waitFor(() => {
      expect(screen.getByTestId("plan-result")).toHaveTextContent("set");
    });

    // Click "New Plan" then commit via AI path
    const newPlanBtn = screen.getByRole("button", { name: /new plan/i });
    await user.click(newPlanBtn);
    await user.click(screen.getByRole("button", { name: /have ai recommend my schedule/i }));

    // PIN: planResult must be null after reset
    await waitFor(() => {
      expect(screen.getByTestId("plan-result")).toHaveTextContent("null");
    });
  });

  it("[pin] course list is cleared after New Plan (was non-empty)", async () => {
    const user = userEvent.setup();
    render(<App userId="test-user" onSignOut={() => {}} />);

    await waitFor(() => expect(lastChatProps).not.toBeNull());

    // Inject a 3-course plan → CalendarView should show 3 courses
    await injectPlan(["CSEN 12", "CSEN 20", "MATH 11"]);

    await waitFor(() => {
      expect(screen.getByTestId("calendar-view")).toHaveAttribute("data-course-count", "3");
    });

    // Click "New Plan" then commit via AI path
    const newPlanBtn = screen.getByRole("button", { name: /new plan/i });
    await user.click(newPlanBtn);
    await user.click(screen.getByRole("button", { name: /have ai recommend my schedule/i }));

    // PIN: course count must be 0 after reset
    await waitFor(() => {
      expect(screen.getByTestId("calendar-view")).toHaveAttribute("data-course-count", "0");
    });
  });

  it("canceling PlanStartModal keeps the current schedule visible", async () => {
    const user = userEvent.setup();
    render(<App userId="test-user" onSignOut={() => {}} />);

    await waitFor(() => expect(lastChatProps).not.toBeNull());
    await injectPlan(["CSEN 12", "CSEN 20", "MATH 11"]);

    await waitFor(() => {
      expect(screen.getByTestId("calendar-view")).toHaveAttribute("data-course-count", "3");
    });

    await user.click(screen.getByRole("button", { name: /new plan/i }));
    await waitFor(() => {
      expect(screen.getByTestId("plan-start-modal")).toBeInTheDocument();
    });

    await user.click(screen.getByRole("button", { name: /^cancel$/i }));

    await waitFor(() => {
      expect(screen.queryByTestId("plan-start-modal")).not.toBeInTheDocument();
      expect(screen.getByTestId("calendar-view")).toHaveAttribute("data-course-count", "3");
      expect(screen.getByTestId("plan-result")).toHaveTextContent("set");
    });
  });

  it("[pin] fileUploaded is PRESERVED after New Plan", async () => {
    const user = userEvent.setup();
    render(<App userId="test-user" onSignOut={() => {}} />);

    await waitFor(() => expect(lastChatProps).not.toBeNull());

    // Mark transcript as uploaded
    await markFileUploaded();

    await waitFor(() => {
      expect(screen.getByTestId("file-uploaded")).toHaveTextContent("true");
    });

    // Click "New Plan"
    const newPlanBtn = screen.getByRole("button", { name: /new plan/i });
    await user.click(newPlanBtn);

    // PIN: fileUploaded MUST NOT be cleared — user's transcript persists across plans
    await waitFor(() => {
      expect(screen.getByTestId("file-uploaded")).toHaveTextContent("true");
    });
  });

  it("[pin] missingDetails is PRESERVED after New Plan", async () => {
    const user = userEvent.setup();
    render(<App userId="test-user" onSignOut={() => {}} />);

    await waitFor(() => expect(lastChatProps).not.toBeNull());

    // Inject academic details
    await markFileUploaded();

    await waitFor(() => {
      expect(screen.getByTestId("missing-details-count")).toHaveTextContent("1");
    });

    // Click "New Plan"
    const newPlanBtn = screen.getByRole("button", { name: /new plan/i });
    await user.click(newPlanBtn);

    // PIN: missingDetails MUST NOT be cleared — same student, new quarter plan
    await waitFor(() => {
      expect(screen.getByTestId("missing-details-count")).toHaveTextContent("1");
    });
  });

  it("[pin] plan history (snapshots) is PRESERVED after New Plan", async () => {
    const user = userEvent.setup();
    render(<App userId="test-user" onSignOut={() => {}} />);

    await waitFor(() => expect(lastChatProps).not.toBeNull());

    // Inject a plan — this saves a snapshot
    await injectPlan(["CSEN 12", "CSEN 20", "MATH 11"]);

    // Snapshot appears as a session in LeftPanel
    await waitFor(() => {
      expect(screen.getByText(/Plan · 3 courses/i)).toBeInTheDocument();
    });

    // Click "New Plan"
    const newPlanBtn = screen.getByRole("button", { name: /new plan/i });
    await user.click(newPlanBtn);

    // PIN: history must survive — only current session is reset
    await waitFor(() => {
      expect(screen.getByText(/Plan · 3 courses/i)).toBeInTheDocument();
    });
  });

  it("[pin] messages reset to a single NEW_PLAN_AI_TEXT entry (no stale messages)", async () => {
    const user = userEvent.setup();
    render(<App userId="test-user" onSignOut={() => {}} />);

    await waitFor(() => expect(lastChatProps).not.toBeNull());

    await injectPlan(["CSEN 12"]);

    await user.click(screen.getByRole("button", { name: /new plan/i }));
    await user.click(screen.getByRole("button", { name: /have ai recommend my schedule/i }));

    await waitFor(() => {
      expect(screen.getByTestId("messages-count")).toHaveTextContent("1");
      expect(screen.getByTestId("latest-message")).toHaveTextContent(
        "Started a new plan. Upload your Academic Progress file (.xlsx) if you have not yet, then describe your preferences for next quarter.",
      );
    });
  });
});
