import {
  useRef,
  useState,
  type ChangeEventHandler,
  type Dispatch,
  type SetStateAction,
} from "react";
import {
  generatePlan,
  uploadTranscript,
} from "../api/client";

export type ChatUiMessage = {
  id: string;
  role: "user" | "assistant";
  content: string;
};

export type ChatPanelProps = {
  userId: string | null;
  missingDetails: unknown[];
  planResult: Record<string, unknown> | null;
  messages: ChatUiMessage[];
  setMessages: Dispatch<SetStateAction<ChatUiMessage[]>>;
  setMissingDetails: (v: unknown[]) => void;
  setPlanResult: (v: Record<string, unknown> | null) => void;
  fileUploaded: boolean;
  setFileUploaded: (v: boolean) => void;
  onPlanGenerated: (plan: Record<string, unknown>) => void;
};

function planSummaryText(plan: Record<string, unknown>): string {
  const recs = (plan.recommended as Record<string, unknown>[]) ?? [];
  const lines = recs.map((x) => {
    const c = String(x.course ?? "?");
    const u = x.units != null ? String(x.units) : "?";
    return `• ${c} (${u} units)`;
  });
  const tu = plan.total_units != null ? String(plan.total_units) : "?";
  const adv =
    typeof plan.advice === "string" && plan.advice.trim()
      ? `\n\n${plan.advice.trim()}`
      : "";
  return `${lines.join("\n")}\n\nTotal: ${tu} units.${adv}`;
}

export function ChatPanel({
  userId,
  missingDetails,
  planResult,
  messages,
  setMessages,
  setMissingDetails,
  setPlanResult,
  fileUploaded,
  setFileUploaded,
  onPlanGenerated,
}: ChatPanelProps) {
  const [input, setInput] = useState("");
  const fileInputRef = useRef<HTMLInputElement>(null);

  const send = async () => {
    const trimmed = input.trim();
    if (!trimmed) return;
    const userMsgId = `u-${Date.now()}`;
    setMessages((m) => [
      ...m,
      { id: userMsgId, role: "user", content: trimmed },
    ]);
    setInput("");

    const lower = trimmed.toLowerCase();
    const mentionsUpload = lower.includes("upload");

    if (
      !fileUploaded &&
      (mentionsUpload || missingDetails.length === 0)
    ) {
      setMessages((m) => [
        ...m,
        {
          id: `a-${Date.now()}`,
          role: "assistant",
          content:
            "Please upload your Academic Progress xlsx file first.",
        },
      ]);
      return;
    }

    if ((missingDetails.length > 0 || fileUploaded) && !planResult) {
      const loadingId = `l-${Date.now()}`;
      setMessages((m) => [
        ...m,
        {
          id: loadingId,
          role: "assistant",
          content: "Planning your schedule...",
        },
      ]);
      try {
        const data = await generatePlan(
          missingDetails as any[],
          trimmed,
          userId ?? "",
        );
        if (!Array.isArray(data.recommended)) {
          throw new Error("Invalid plan response from server.");
        }
        setPlanResult(data);
        onPlanGenerated(data);
        const summary = planSummaryText(data);
        setMessages((m) =>
          m.map((msg) =>
            msg.id === loadingId
              ? {
                  ...msg,
                  content: `Here's your recommended schedule for next quarter:\n\n${summary}`,
                }
              : msg,
          ),
        );
      } catch (e) {
        const msg = e instanceof Error ? e.message : String(e);
        setMessages((m) =>
          m.map((row) =>
            row.id === loadingId
              ? {
                  ...row,
                  content: `Could not generate a plan: ${msg}`,
                }
              : row,
          ),
        );
      }
      return;
    }

    if (planResult) {
      const loadingId = `l-${Date.now()}`;
      setMessages((m) => [
        ...m,
        {
          id: loadingId,
          role: "assistant",
          content: "Planning your schedule...",
        },
      ]);
      try {
        const data = await generatePlan(
          missingDetails as any[],
          trimmed,
          userId ?? "",
        );
        if (!Array.isArray(data.recommended)) {
          throw new Error("Invalid plan response from server.");
        }
        setPlanResult(data);
        onPlanGenerated(data);
        const summary = planSummaryText(data);
        setMessages((m) =>
          m.map((msg) =>
            msg.id === loadingId
              ? {
                  ...msg,
                  content: `Here's your updated schedule:\n\n${summary}`,
                }
              : msg,
          ),
        );
      } catch (e) {
        const msg = e instanceof Error ? e.message : String(e);
        setMessages((m) =>
          m.map((row) =>
            row.id === loadingId
              ? {
                  ...row,
                  content: `Could not update the plan: ${msg}`,
                }
              : row,
          ),
        );
      }
    }
  };

  const onFilePick = () => fileInputRef.current?.click();

  const onFileChange: ChangeEventHandler<HTMLInputElement> = (e) => {
    const f = e.target.files?.[0];
    e.target.value = "";
    if (!f) return;

    const name = f.name.toLowerCase();
    if (name.endsWith(".pdf")) {
      setMessages((m) => [
        ...m,
        {
          id: `a-${Date.now()}`,
          role: "assistant",
          content: "PDF analysis coming soon",
        },
      ]);
      return;
    }

    if (!name.endsWith(".xlsx") && !name.endsWith(".xlsm")) {
      setMessages((m) => [
        ...m,
        {
          id: `a-${Date.now()}`,
          role: "assistant",
          content: "Please upload an .xlsx Academic Progress export.",
        },
      ]);
      return;
    }

    void (async () => {
      try {
        const data = await uploadTranscript(f);
        const md = (data.missing_details as unknown[]) ?? [];
        setMissingDetails(md);
        setFileUploaded(true);
        const n = md.length;
        setMessages((m) => [
          ...m,
          {
            id: `a-${Date.now()}`,
            role: "assistant",
            content: `Got it! I found ${n} missing requirements. What are your preferences for next quarter?`,
          },
        ]);
      } catch (err) {
        const msg = err instanceof Error ? err.message : String(err);
        setMessages((m) => [
          ...m,
          {
            id: `a-${Date.now()}`,
            role: "assistant",
            content: `Upload failed: ${msg}`,
          },
        ]);
      }
    })();
  };

  return (
    <aside className="flex w-[380px] shrink-0 flex-col border-l border-neutral-200 bg-[var(--scu-white)] shadow-sm">
      <div className="shrink-0 border-b border-neutral-200 px-4 py-3">
        <h2 className="text-sm font-semibold text-[var(--scu-text)]">
          SCU Course Planner
        </h2>
      </div>

      <div className="min-h-0 flex-1 space-y-3 overflow-y-auto px-4 py-4">
        {messages.map((msg) => (
          <div
            key={msg.id}
            className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}
          >
            <div
              className={`max-w-[90%] rounded-lg px-3 py-2 text-sm leading-relaxed ${
                msg.role === "user"
                  ? "bg-neutral-100 text-[var(--scu-text)]"
                  : "bg-[var(--scu-gray)] text-[var(--scu-text)] ring-1 ring-neutral-200"
              }`}
            >
              {msg.content}
            </div>
          </div>
        ))}
      </div>

      <div className="shrink-0 border-t border-neutral-200 p-3">
        <input
          ref={fileInputRef}
          type="file"
          accept=".pdf,.xlsx,.xlsm,application/pdf,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
          className="hidden"
          onChange={onFileChange}
        />
        <div className="flex items-end gap-2">
          <textarea
            rows={2}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                void send();
              }
            }}
            placeholder="Message…"
            className="min-h-[44px] flex-1 resize-none rounded-md border border-neutral-300 px-3 py-2 text-sm text-[var(--scu-text)] outline-none ring-0 placeholder:text-neutral-400 focus:border-[var(--scu-red)] focus:ring-1 focus:ring-[var(--scu-red)]"
          />
          <div className="flex flex-col gap-1">
            <button
              type="button"
              onClick={onFilePick}
              className="rounded-md p-2 text-neutral-500 hover:bg-neutral-100 hover:text-[var(--scu-text)]"
              title="Attach PDF or Excel"
              aria-label="Attach PDF or Excel"
            >
              <PaperclipIcon />
            </button>
            <button
              type="button"
              onClick={() => {
                /* voice placeholder */
              }}
              className="rounded-md p-2 text-neutral-500 hover:bg-neutral-100 hover:text-[var(--scu-text)]"
              title="Voice (coming soon)"
              aria-label="Voice input placeholder"
            >
              <MicIcon />
            </button>
          </div>
          <button
            type="button"
            onClick={() => void send()}
            className="h-[44px] shrink-0 rounded-md bg-[var(--scu-red)] px-4 text-sm font-semibold text-white shadow-sm transition hover:bg-[var(--scu-dark-red)]"
          >
            Send
          </button>
        </div>
        <p className="mt-2 text-[10px] text-neutral-400">
          PDF and .xlsx only (mock). Voice is not connected.
        </p>
      </div>
    </aside>
  );
}

function PaperclipIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" aria-hidden>
      <path
        d="M21.44 11.05L12.25 20.24C11.1242 21.3658 9.59723 21.9983 8.005 21.9983C6.41277 21.9983 4.88579 21.3658 3.76 20.24C2.63421 19.1142 2.00174 17.5872 2.00174 15.995C2.00174 14.4028 2.63421 12.8758 3.76 11.75L12.95 2.56C13.7006 1.80943 14.7186 1.38776 15.78 1.38776C16.8415 1.38776 17.8594 1.80943 18.61 2.56C19.3606 3.31057 19.7823 4.32855 19.7823 5.39C19.7823 6.45145 19.3606 7.46943 18.61 8.22L9.41 17.41C9.03481 17.7852 8.52574 17.9961 7.995 17.9961C7.46426 17.9961 6.95519 17.7852 6.58 17.41C6.20481 17.0348 5.9939 16.5257 5.9939 15.995C5.9939 15.4643 6.20481 14.9552 6.58 14.58L15.37 5.79"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function MicIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" aria-hidden>
      <path
        d="M12 1C10.34 1 9 2.34 9 4V12C9 13.66 10.34 15 12 15C13.66 15 15 13.66 15 12V4C15 2.34 13.66 1 12 1Z"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <path
        d="M19 10V12C19 15.87 15.87 19 12 19C8.13 19 5 15.87 5 12V10"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <path
        d="M12 19V23M8 23H16"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}
