import React, { useCallback, useState } from "react";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { ChatPanel, type ChatUiMessage } from "../../web/src/components/ChatPanel";
import type { ParsedRow } from "../../web/src/types";

const generatePlan = vi.fn();

vi.mock("../../web/src/api/client", () => ({
  generatePlan: (...args: unknown[]) => generatePlan(...args),
  transcribeAudio: vi.fn(),
  uploadTranscript: vi.fn(),
}));

function ChatPanelHarness({
  initialMajorConfirmed = false,
}: {
  initialMajorConfirmed?: boolean;
}) {
  const [majorConfirmed, setMajorConfirmed] = useState(initialMajorConfirmed);
  const [messages, setMessages] = useState<ChatUiMessage[]>([
    { id: "m0", role: "assistant", content: "Welcome" },
  ]);
  const [missingDetails] = useState<unknown[]>([{ requirement: "CSEN 174" }]);
  const [parsedRows] = useState<ParsedRow[]>([]);
  const noop = useCallback(() => {}, []);
  const setMissingDetails = noop;
  const setPlanResult = noop;
  const onPlanGenerated = noop;
  const setFileUploaded = noop;

  return (
    <>
      <button type="button" onClick={() => setMajorConfirmed(true)}>
        Confirm major
      </button>
      <ChatPanel
        userId="user-1"
        parsedRows={parsedRows}
        missingDetails={missingDetails}
        planResult={null}
        messages={messages}
        setMessages={setMessages}
        setMissingDetails={setMissingDetails}
        setPlanResult={setPlanResult}
        fileUploaded={true}
        setFileUploaded={setFileUploaded}
        onPlanGenerated={onPlanGenerated}
        studentMajorId="csen"
        majorConfirmed={majorConfirmed}
      />
    </>
  );
}

describe("ChatPanel major confirmation gate", () => {
  beforeAll(() => {
    Element.prototype.scrollIntoView = vi.fn();
  });

  beforeEach(() => {
    generatePlan.mockReset();
    generatePlan.mockResolvedValue({
      type: "plan",
      recommended: [{ course: "CSEN 174", units: 4 }],
      total_units: 4,
      assistant_reply: "Here is your plan.",
    });
  });

  it("calls generatePlan immediately after major is confirmed without an extra chat turn", async () => {
    const user = userEvent.setup();
    render(<ChatPanelHarness />);

    await user.click(screen.getByRole("button", { name: "Confirm major" }));

    const textarea = screen.getByPlaceholderText("Message…");
    await user.type(textarea, "Plan my schedule for next quarter");
    await user.click(screen.getByRole("button", { name: "Send" }));

    expect(screen.queryByText(/专业确认栏/)).not.toBeInTheDocument();
    await waitFor(() => {
      expect(generatePlan).toHaveBeenCalledTimes(1);
    });
  });
});
