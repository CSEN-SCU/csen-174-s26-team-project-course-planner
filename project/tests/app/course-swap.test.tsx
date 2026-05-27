import React from "react";
import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import App from "../../web/src/App";
import type { ChatPanelProps } from "../../web/src/components/ChatPanel";

vi.mock("../../web/src/api/client", () => ({
  getMemory: vi.fn(async () => ({ memories: [] })),
  saveMemory: vi.fn(async () => ({ id: 1 })),
  deleteMemory: vi.fn(async () => {}),
  deleteAllUserData: vi.fn(async () => {}),
  generateFourYearPlan: vi.fn(async () => ({ plan: null })),
  searchCatalogSections: vi.fn(async () => ({
    sections: [
      {
        course_section: "CSEN 12 - 2",
        course: "CSEN 12",
        section: 2,
        subject: "CSEN",
        number: "12",
        title: "Intro to Programming",
        units: 4,
        status: "Open",
        enrolled_capacity: null,
        instructors: ["Prof B"],
        meeting_days: [1, 3],
        meeting_start_min: 120,
        meeting_end_min: 210,
        meeting_pattern: "T Th | 10:00 AM - 11:30 AM",
        location: null,
        course_tags: [],
        lab_partner: null,
      },
    ],
    total: 1,
    count: 1,
    facets: { subjects: [], tags: { Core: [], Other: [] }, meeting_times: [] },
  })),
  suggestCoursesForSlot: vi.fn(async () => ({ candidates: [], count: 0 })),
  googleSignInUrl: vi.fn(() => ""),
}));

vi.mock("../../web/src/auth/session", () => ({
  clearLocalSession: vi.fn(),
}));

let lastChatProps: ChatPanelProps | null = null;
let lastCalendarProps: any = null;

vi.mock("../../web/src/components/ChatPanel", () => ({
  ChatPanel: (props: ChatPanelProps) => {
    lastChatProps = props;
    return <div data-testid="chat-panel" />;
  },
}));

vi.mock("../../web/src/components/CalendarView", () => ({
  CalendarView: (props: any) => {
    lastCalendarProps = props;
    const first = props.recommendedCourses?.[0] ?? {};
    return (
      <div data-testid="calendar-view">
        <div data-testid="first-course-prof">{String(first.best_professor ?? "")}</div>
        <div data-testid="first-course-start">{String(first.meeting_start_min ?? "")}</div>
        <div data-testid="course-count">{String((props.recommendedCourses ?? []).length)}</div>
        <button
          type="button"
          onClick={() => props.onCourseClick?.(0, "CSEN 12", 100, 120)}
        >
          open-course-actions
        </button>
      </div>
    );
  },
}));

vi.mock("../../web/src/components/CourseSwapModal", () => ({
  CourseSwapModal: (props: any) =>
    props.open ? (
      <div data-testid="course-swap-modal">
        <button
          type="button"
          onClick={() =>
            props.onSwap({
              course: "CSEN 12",
              section: 2,
              title: "Intro to Programming",
              units: 4,
              instructors: ["Prof B"],
              meeting_days: [1, 3],
              meeting_start_min: 120,
              meeting_end_min: 210,
            })
          }
        >
          swap-to-section-2
        </button>
        <button type="button" onClick={props.onRemove}>
          remove-course
        </button>
      </div>
    ) : null,
}));

vi.mock("../../web/src/components/FourYearPlanView", () => ({
  FourYearPlanView: () => <div />,
}));
vi.mock("../../web/src/components/SlotSuggestionPopover", () => ({
  SlotSuggestionPopover: () => null,
}));
vi.mock("../../web/src/components/CourseBrowser", () => ({
  CourseBrowser: () => null,
}));
vi.mock("../../web/src/components/PlanStartModal", () => ({
  PlanStartModal: () => null,
}));
vi.mock("../../web/src/components/SlotActionModal", () => ({
  SlotActionModal: () => null,
}));
vi.mock("../../web/src/components/DeleteUserDataConfirm", () => ({
  DeleteUserDataConfirm: () => null,
}));
vi.mock("../../web/src/components/FirstLoginCarousel", () => ({
  FirstLoginCarousel: () => null,
}));
vi.mock("../../web/src/components/SiteFooter", () => ({
  SiteFooter: () => null,
}));

async function injectPlan() {
  const plan: Record<string, unknown> = {
    recommended: [
      {
        course: "CSEN 12",
        title: "Intro to Programming",
        units: 4,
        best_professor: "Prof A",
        meeting_days: [0, 2],
        meeting_start_min: 60,
        meeting_end_min: 150,
      },
    ],
    total_units: 4,
  };
  await act(async () => {
    lastChatProps!.setPlanResult(plan);
    lastChatProps!.onPlanGenerated(plan, [
      { id: "m1", role: "assistant", content: "Plan ready" },
    ]);
  });
}

describe("course swap actions", () => {
  beforeEach(() => {
    lastChatProps = null;
    lastCalendarProps = null;
  });

  it("opens course actions and swaps to another section", async () => {
    const user = userEvent.setup();
    render(<App userId="u1" onSignOut={() => {}} />);
    await waitFor(() => expect(lastChatProps).not.toBeNull());
    await injectPlan();

    await user.click(screen.getByRole("button", { name: "open-course-actions" }));
    await waitFor(() =>
      expect(screen.getByTestId("course-swap-modal")).toBeInTheDocument(),
    );
    await user.click(screen.getByRole("button", { name: "swap-to-section-2" }));

    await waitFor(() => {
      expect(screen.getByTestId("first-course-prof")).toHaveTextContent("Prof B");
      expect(screen.getByTestId("first-course-start")).toHaveTextContent("120");
    });
  });

  it("removes course from schedule from actions modal", async () => {
    const user = userEvent.setup();
    render(<App userId="u1" onSignOut={() => {}} />);
    await waitFor(() => expect(lastChatProps).not.toBeNull());
    await injectPlan();

    await user.click(screen.getByRole("button", { name: "open-course-actions" }));
    await user.click(screen.getByRole("button", { name: "remove-course" }));

    await waitFor(() => {
      expect(screen.getByTestId("course-count")).toHaveTextContent("0");
    });
  });
});
