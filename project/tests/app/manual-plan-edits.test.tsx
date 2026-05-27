import React from "react";
import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import App from "../../web/src/App";
import { saveMemory } from "../../web/src/api/client";
import type { ChatPanelProps } from "../../web/src/components/ChatPanel";
import type { CatalogSection } from "../../web/src/api/client";

vi.mock("../../web/src/api/client", () => ({
  getMemory: vi.fn(async () => ({ memories: [] })),
  saveMemory: vi.fn(async () => ({ id: 101 })),
  deleteMemory: vi.fn(async () => {}),
  deleteAllUserData: vi.fn(async () => {}),
  generateFourYearPlan: vi.fn(async () => ({ plan: null })),
  listCourses: vi.fn(async () => []),
  googleSignInUrl: vi.fn(() => ""),
}));

vi.mock("../../web/src/auth/session", () => ({
  clearLocalSession: vi.fn(),
}));

let lastChatProps: ChatPanelProps | null = null;

vi.mock("../../web/src/components/ChatPanel", () => ({
  ChatPanel: (props: ChatPanelProps) => {
    lastChatProps = props;
    const recs = Array.isArray(props.planResult?.recommended)
      ? (props.planResult.recommended as Record<string, unknown>[])
      : [];
    return (
      <div data-testid="chat-panel">
        <div data-testid="chat-plan-courses">
          {recs.map((r) => String(r.course ?? "")).join(",")}
        </div>
      </div>
    );
  },
}));

vi.mock("../../web/src/components/CalendarView", () => ({
  CalendarView: (props: {
    recommendedCourses: Record<string, unknown>[];
    onRemoveCourse?: (idx: number) => void;
  }) => (
    <div
      data-testid="calendar-view"
      data-course-count={(props.recommendedCourses || []).length}
    >
      {(props.recommendedCourses || []).map((course, idx) => (
        <button
          key={String(course.course ?? idx)}
          type="button"
          data-testid={`remove-${idx}`}
          onClick={() => props.onRemoveCourse?.(idx)}
        >
          remove {String(course.course ?? idx)}
        </button>
      ))}
    </div>
  ),
}));

const catalogCourse: CatalogSection = {
  course: "CSEN 174",
  title: "Software Engineering",
  section: "1001",
  units: 4,
  instructors: ["Prof A"],
  meeting_days: ["Mon"],
  meeting_start_min: 60,
  meeting_end_min: 110,
};

vi.mock("../../web/src/components/CourseBrowser", () => ({
  CourseBrowser: (props: { onAdd: (sections: CatalogSection[]) => void }) => (
    <button
      type="button"
      data-testid="catalog-add"
      onClick={() => props.onAdd([catalogCourse])}
    >
      add catalog course
    </button>
  ),
}));

vi.mock("../../web/src/components/FourYearPlanView", () => ({
  FourYearPlanView: () => <div data-testid="four-year-view" />,
}));

vi.mock("../../web/src/components/SlotSuggestionPopover", () => ({
  SlotSuggestionPopover: () => null,
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

async function injectPlan(courses: string[]) {
  expect(lastChatProps).not.toBeNull();
  const plan: Record<string, unknown> = {
    recommended: courses.map((course) => ({ course, units: 4 })),
    total_units: courses.length * 4,
  };
  await act(async () => {
    lastChatProps!.setPlanResult(plan);
    lastChatProps!.onPlanGenerated(plan, [
      { id: "a0", role: "assistant", content: "Here is your plan." },
    ]);
  });
}

describe("manual plan edits", () => {
  beforeEach(() => {
    lastChatProps = null;
    vi.mocked(saveMemory).mockClear();
  });

  it("promotes manually added catalog courses into the canonical plan and persisted snapshot", async () => {
    const user = userEvent.setup();
    render(<App userId="manual-user" onSignOut={() => {}} />);

    await waitFor(() => expect(lastChatProps).not.toBeNull());
    await user.click(screen.getByTestId("catalog-add"));

    await waitFor(() => {
      expect(screen.getByTestId("calendar-view")).toHaveAttribute("data-course-count", "1");
      expect(screen.getByTestId("chat-plan-courses")).toHaveTextContent("CSEN 174");
    });

    await waitFor(() => expect(saveMemory).toHaveBeenCalled());
    const latestSave = vi.mocked(saveMemory).mock.calls.at(-1);
    expect(latestSave?.[1]).toBe("plan_outcome");
    const saved = JSON.parse(String(latestSave?.[2] ?? "{}")) as {
      recommended?: Record<string, unknown>[];
    };
    expect(saved.recommended?.map((r) => r.course)).toEqual(["CSEN 174"]);
  });

  it("keeps removed courses out of the canonical plan used by later chat turns", async () => {
    const user = userEvent.setup();
    render(<App userId="manual-user" onSignOut={() => {}} />);

    await waitFor(() => expect(lastChatProps).not.toBeNull());
    await injectPlan(["CSEN 12", "MATH 11"]);

    await waitFor(() => {
      expect(screen.getByTestId("calendar-view")).toHaveAttribute("data-course-count", "2");
    });
    await user.click(screen.getByTestId("remove-0"));

    await waitFor(() => {
      expect(screen.getByTestId("calendar-view")).toHaveAttribute("data-course-count", "1");
      expect(screen.getByTestId("chat-plan-courses")).toHaveTextContent("MATH 11");
      expect(screen.getByTestId("chat-plan-courses")).not.toHaveTextContent("CSEN 12");
    });
  });
});
