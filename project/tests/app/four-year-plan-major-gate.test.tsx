/**
 * Regression: confirming major must refresh the 4-year generate handler.
 * Previously handleGenerateFourYearPlan omitted majorConfirmed from its deps,
 * so clicking Generate right after confirm could still see majorConfirmed=false.
 */

import React from "react";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import App from "../../web/src/App";
import type { ChatPanelProps } from "../../web/src/components/ChatPanel";

const apiMocks = vi.hoisted(() => ({
  getMemory: vi.fn(async () => ({ memories: [] })),
  generateFourYearPlan: vi.fn(async () => ({
    quarters: [],
    graduation_term: "Spring 2030",
    total_remaining_units: 120,
    advice: "Sample plan",
  })),
}));

vi.mock("../../web/src/api/client", () => ({
  getMemory: apiMocks.getMemory,
  saveMemory: vi.fn(async () => ({ id: 1 })),
  deleteMemory: vi.fn(async () => {}),
  deleteAllUserData: vi.fn(async () => {}),
  generateFourYearPlan: apiMocks.generateFourYearPlan,
  generatePlan: vi.fn(async () => ({ recommended: [] })),
  listCourses: vi.fn(async () => []),
  googleSignInUrl: vi.fn(() => ""),
  listMajors: vi.fn(async () => ({
    majors: [{ major_id: "csen", name: "Computer Science and Engineering" }],
  })),
  confirmStudentMajor: vi.fn(async () => ({})),
  detectStudentMajor: vi.fn(async () => ({
    major_id: "csen",
    name: "Computer Science and Engineering",
    confidence: "high",
  })),
}));

vi.mock("../../web/src/auth/session", () => ({
  clearLocalSession: vi.fn(),
}));

vi.mock("../../web/src/components/FirstLoginCarousel", () => ({
  FirstLoginCarousel: () => null,
}));

vi.mock("../../web/src/components/CalendarView", () => ({
  CalendarView: () => <div data-testid="calendar-view" />,
}));

vi.mock("../../web/src/components/FourYearPlanView", () => ({
  FourYearPlanView: () => <div data-testid="four-year-view" />,
}));

vi.mock("../../web/src/components/ChatPanel", () => ({
  ChatPanel: (props: ChatPanelProps) => (
    <div data-testid="chat-panel">
      <div data-testid="major-confirmed">{String(props.majorConfirmed)}</div>
      <button
        type="button"
        onClick={() => {
          props.onSelectMajor?.("csen", "Computer Science and Engineering");
          props.onMajorConfirmed?.();
        }}
      >
        Confirm major for test
      </button>
    </div>
  ),
}));

describe("four-year plan major confirmation gate", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.setItem("scu-planner-intro-seen-test-user", "1");
    apiMocks.getMemory.mockResolvedValue({
      memories: [
        {
          id: 1,
          kind: "academic_progress",
          content: JSON.stringify([{ requirement: "CSEN 10", status: "Not Satisfied" }]),
        },
        {
          id: 2,
          kind: "parsed_rows",
          content: JSON.stringify([]),
        },
      ],
    });
  });

  it("calls generateFourYearPlan after major is confirmed in the same session", async () => {
    const user = userEvent.setup();
    render(<App userId="test-user" onSignOut={() => {}} onDeleteUserData={() => {}} />);

    await waitFor(() => {
      expect(screen.getByTestId("major-confirmed")).toHaveTextContent("false");
    });

    await user.click(screen.getByRole("button", { name: /confirm major for test/i }));

    await waitFor(() => {
      expect(screen.getByTestId("major-confirmed")).toHaveTextContent("true");
    });

    await user.click(screen.getByRole("button", { name: /four-year plan/i }));
    await user.click(screen.getByRole("button", { name: /generate plan/i }));

    await waitFor(() => {
      expect(apiMocks.generateFourYearPlan).toHaveBeenCalled();
    });

    expect(screen.queryByText(/confirm your major in the chat panel/i)).not.toBeInTheDocument();
  });
});
