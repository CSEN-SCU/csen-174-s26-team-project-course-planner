import React from "react";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
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

  it("discarding a pending transcript update clears transcript state and asks the user to start again", async () => {
    const user = userEvent.setup();
    const setMissingDetails = vi.fn();
    const setParsedRows = vi.fn();
    const setFileUploaded = vi.fn();
    const setPlanResult = vi.fn();
    const onTranscriptUploaded = vi.fn();

    function Harness() {
      const [messages, setMessages] = React.useState([
        {
          id: "m0",
          role: "assistant" as const,
          content: "Your Academic Progress is already loaded.",
        },
      ]);

      return (
        <ChatPanel
          userId="test-user"
          parsedRows={[{ course_code: "CSEN 10", status: "Satisfied" }]}
          missingDetails={[{ requirement: "Core" }]}
          planResult={{ recommended: [{ course: "CSEN 10" }] }}
          messages={messages}
          setMessages={setMessages}
          setMissingDetails={setMissingDetails}
          setPlanResult={setPlanResult}
          fileUploaded={true}
          setFileUploaded={setFileUploaded}
          onPlanGenerated={() => {}}
          setParsedRows={setParsedRows}
          onTranscriptUploaded={onTranscriptUploaded}
        />
      );
    }

    const { container } = render(<Harness />);
    const input = container.querySelector('input[type="file"]') as HTMLInputElement;
    const replacement = new File(["replacement"], "replacement.xlsx", {
      type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    });

    await user.upload(input, replacement);
    expect(screen.getByText(/Would you like to update it with the new file/i)).toBeInTheDocument();

    await user.type(screen.getByPlaceholderText("Message…"), "no");
    await user.click(screen.getByRole("button", { name: "Send" }));

    await waitFor(() => {
      expect(setMissingDetails).toHaveBeenCalledWith([]);
      expect(setParsedRows).toHaveBeenCalledWith([]);
      expect(setFileUploaded).toHaveBeenCalledWith(false);
      expect(setPlanResult).toHaveBeenCalledWith(null);
      expect(onTranscriptUploaded).toHaveBeenCalledWith(null);
    });
    expect(screen.getByText(/Please upload your Academic Progress again/i)).toBeInTheDocument();
  });
});
