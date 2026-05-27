import React from "react";
import { render, screen } from "@testing-library/react";
import { beforeAll, describe, expect, it, vi } from "vitest";
import { ChatPanel } from "../../web/src/components/ChatPanel";

vi.mock("../../web/src/api/client", () => ({
  generatePlan: vi.fn(),
  transcribeAudio: vi.fn(),
  uploadTranscript: vi.fn(),
}));

describe("ChatPanel academic progress state", () => {
  beforeAll(() => {
    Element.prototype.scrollIntoView = vi.fn();
  });

  it("shows saved-progress copy instead of upload instructions when a transcript is loaded", () => {
    render(
      <ChatPanel
        userId="test-user"
        parsedRows={[{ course_code: "CSEN 10", status: "Satisfied" }]}
        missingDetails={[]}
        planResult={null}
        messages={[
          {
            id: "m0",
            role: "assistant",
            content: "Your Academic Progress is already loaded.",
          },
        ]}
        setMessages={() => {}}
        setMissingDetails={() => {}}
        setPlanResult={() => {}}
        fileUploaded={true}
        setFileUploaded={() => {}}
        onPlanGenerated={() => {}}
        setParsedRows={() => {}}
      />,
    );

    expect(screen.getByText(/Academic Progress is saved/i)).toBeInTheDocument();
    expect(screen.queryByText(/Drag and drop your Academic Progress/i)).not.toBeInTheDocument();
  });
});
