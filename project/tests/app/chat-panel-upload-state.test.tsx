import React from "react";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeAll, describe, expect, it, vi } from "vitest";
import { ChatPanel } from "../../web/src/components/ChatPanel";
import { uploadTranscript } from "../../web/src/api/client";

vi.mock("../../web/src/api/client", () => ({
  generatePlan: vi.fn(),
  transcribeAudio: vi.fn(),
  uploadTranscript: vi.fn(),
}));

const mockedUploadTranscript = vi.mocked(uploadTranscript);

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
    const onDiscardTranscript = vi.fn();

    function Harness() {
      const [messages, setMessages] = React.useState([
        {
          id: "m0",
          role: "assistant" as const,
          content: "Your Academic Progress is already loaded.",
        },
        {
          id: "m1",
          role: "user" as const,
          content: "Plan my fall quarter.",
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
          onDiscardTranscript={onDiscardTranscript}
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
    expect(screen.queryByText(/Reply \*\*yes\*\*/i)).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "No" }));

    await waitFor(() => {
      expect(setMissingDetails).toHaveBeenCalledWith([]);
      expect(setParsedRows).toHaveBeenCalledWith([]);
      expect(setFileUploaded).toHaveBeenCalledWith(false);
      expect(setPlanResult).toHaveBeenCalledWith(null);
      expect(onTranscriptUploaded).toHaveBeenCalledWith(null);
      expect(onDiscardTranscript).toHaveBeenCalled();
    });
    expect(screen.getByText(/Please upload your Academic Progress again/i)).toBeInTheDocument();
  });

  it("allows re-upload via paperclip after discarding a pending transcript update", async () => {
    const user = userEvent.setup();
    mockedUploadTranscript.mockResolvedValue({
      missing_details: [{ requirement: "Core" }],
      parsed_rows: [{ course_code: "CSEN 20", status: "Satisfied" }],
      major_detection: { major_id: "csen", name: "CSEN" },
    });

    function Harness() {
      const [messages, setMessages] = React.useState([
        {
          id: "m0",
          role: "assistant" as const,
          content: "Your Academic Progress is already loaded.",
        },
        {
          id: "m1",
          role: "user" as const,
          content: "Plan my fall quarter.",
        },
      ]);
      const [fileUploaded, setFileUploaded] = React.useState(true);

      return (
        <ChatPanel
          userId="test-user"
          parsedRows={[{ course_code: "CSEN 10", status: "Satisfied" }]}
          missingDetails={[{ requirement: "Core" }]}
          planResult={{ recommended: [{ course: "CSEN 10" }] }}
          messages={messages}
          setMessages={setMessages}
          setMissingDetails={() => {}}
          setPlanResult={() => {}}
          fileUploaded={fileUploaded}
          setFileUploaded={setFileUploaded}
          onPlanGenerated={() => {}}
          setParsedRows={() => {}}
        />
      );
    }

    const { container } = render(<Harness />);
    const fileInput = container.querySelector('input[type="file"]') as HTMLInputElement;
    const replacement = new File(["replacement"], "replacement.xlsx", {
      type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    });
    const fresh = new File(["fresh"], "fresh.xlsx", {
      type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    });

    await user.upload(fileInput, replacement);
    await user.click(screen.getByRole("button", { name: "No" }));

    mockedUploadTranscript.mockClear();
    await user.upload(fileInput, fresh);

    await waitFor(() => {
      expect(mockedUploadTranscript).toHaveBeenCalledWith(fresh, "test-user");
      expect(screen.getByText(/Found 1 missing requirements/i)).toBeInTheDocument();
    });
  });
});
