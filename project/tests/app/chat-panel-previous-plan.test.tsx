import React from "react";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { ChatPanel } from "../../web/src/components/ChatPanel";
import { generatePlan } from "../../web/src/api/client";

vi.mock("../../web/src/api/client", () => ({
  generatePlan: vi.fn(),
  transcribeAudio: vi.fn(),
  uploadTranscript: vi.fn(),
}));

const mockedGeneratePlan = vi.mocked(generatePlan);

describe("ChatPanel previous_plan baseline", () => {
  beforeAll(() => {
    Element.prototype.scrollIntoView = vi.fn();
  });

  beforeEach(() => {
    mockedGeneratePlan.mockReset();
    mockedGeneratePlan.mockResolvedValue({
      type: "plan",
      recommended: [{ course: "CSEN 10", units: 4 }],
      total_units: 4,
      advice: "",
      assistant_reply: "ok",
    });
  });

  it("sends previousPlanForApi (manual edits) instead of stale planResult", async () => {
    const user = userEvent.setup();
    const stalePlan = {
      recommended: [{ course: "CSEN 10", units: 4 }],
      total_units: 4,
    };
    const baseline = {
      recommended: [
        { course: "CSEN 10", units: 4 },
        { course: "CHIN 1", units: 5, _manualAdd: true },
      ],
      total_units: 9,
    };

    render(
      <ChatPanel
        userId="42"
        parsedRows={[{ course_code: "CSEN 10", status: "Satisfied" }]}
        missingDetails={[{ requirement: "Core" }]}
        planResult={stalePlan}
        previousPlanForApi={baseline}
        messages={[]}
        setMessages={() => {}}
        setMissingDetails={() => {}}
        setPlanResult={() => {}}
        fileUploaded={true}
        setFileUploaded={() => {}}
        onPlanGenerated={() => {}}
        setParsedRows={() => {}}
        studentMajorId="csen"
        majorConfirmed
      />,
    );

    const input = screen.getByRole("textbox");
    await user.type(input, "drop CSEN 194");
    await user.click(screen.getByRole("button", { name: "Send" }));

    await waitFor(() => expect(mockedGeneratePlan).toHaveBeenCalled());
    expect(mockedGeneratePlan.mock.calls[0]?.[3]).toEqual(baseline);
  });
});
