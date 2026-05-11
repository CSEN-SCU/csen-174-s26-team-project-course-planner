import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type ChangeEventHandler,
  type Dispatch,
  type SetStateAction,
} from "react";
import { generatePlan, transcribeAudio, uploadTranscript } from "../api/client";

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
  prefillInput?: string | null;
  onPrefillConsumed?: () => void;
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


// Pick the MIME type the browser supports
function getBestMimeType(): string {
  const candidates = [
    "audio/webm;codecs=opus",
    "audio/ogg;codecs=opus",
    "audio/mp4",
    "audio/webm",
  ];
  for (const t of candidates) {
    if (MediaRecorder.isTypeSupported(t)) return t;
  }
  return "";
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
  prefillInput,
  onPrefillConsumed,
}: ChatPanelProps) {
  const [input, setInput] = useState("");
  const [isGenerating, setIsGenerating] = useState(false);
  const [isListening, setIsListening] = useState(false);
  const [voiceStatus, setVoiceStatus] = useState<"idle" | "recording" | "processing">("idle");
  const [pendingFile, setPendingFile] = useState<File | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, isGenerating]);

  useEffect(() => {
    if (prefillInput) {
      setInput(prefillInput);
      onPrefillConsumed?.();
      setTimeout(() => textareaRef.current?.focus(), 0);
    }
  }, [prefillInput, onPrefillConsumed]);

  const processFile = useCallback(async (f: File) => {
    try {
      const data = await uploadTranscript(f, userId ?? undefined);
      const md = (data.missing_details as unknown[]) ?? [];
      setMissingDetails(md);
      setFileUploaded(true);
      const reply = `Got it! Found ${md.length} missing requirements${userId ? " and saved your progress" : ""}. What are your preferences for next quarter?`;
      setMessages((m) => [...m, { id: `a-${Date.now()}`, role: "assistant", content: reply }]);
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      setMessages((m) => [...m, { id: `a-${Date.now()}`, role: "assistant", content: `Upload failed: ${msg}` }]);
    }
  }, [userId, setMissingDetails, setFileUploaded, setMessages]);

  const sendText = useCallback(async (text: string) => {
    const trimmed = text.trim();
    if (!trimmed) return;

    setMessages((m) => [
      ...m,
      { id: `u-${Date.now()}`, role: "user", content: trimmed },
    ]);

    const lower = trimmed.toLowerCase();

    // Handle pending transcript update confirmation
    if (pendingFile) {
      if (lower === "yes" || lower.startsWith("yes") || lower.includes("update")) {
        const f = pendingFile;
        setPendingFile(null);
        await processFile(f);
        return;
      } else {
        setPendingFile(null);
        setMessages((m) => [...m, { id: `a-${Date.now()}`, role: "assistant", content: "Got it — keeping your existing academic progress." }]);
        return;
      }
    }

    setIsGenerating(true);
    try {
      const data = await generatePlan(
        missingDetails as never[],
        trimmed,
        userId ?? "",
        planResult,
      );

      // Conversational answer — don't touch the calendar
      if (data.type === "answer") {
        const reply = typeof data.reply === "string" && data.reply.trim()
          ? data.reply.trim()
          : "I'm not sure how to answer that. Try asking me to plan your schedule.";
        setMessages((m) => [...m, { id: `a-${Date.now()}`, role: "assistant", content: reply }]);
        return;
      }

      // Planning response
      if (!Array.isArray(data.recommended)) {
        throw new Error("Invalid plan response from server.");
      }
      setPlanResult(data);
      onPlanGenerated(data);

      const assistantReply =
        typeof data.assistant_reply === "string" && data.assistant_reply.trim()
          ? data.assistant_reply.trim()
          : planResult
          ? `Here's your updated schedule:\n\n${planSummaryText(data)}`
          : `Here's your recommended schedule for next quarter:\n\n${planSummaryText(data)}`;

      const displayText =
        typeof data.assistant_reply === "string" && data.assistant_reply.trim()
          ? `${data.assistant_reply.trim()}\n\n${planSummaryText(data)}`
          : assistantReply;

      setMessages((m) => [...m, { id: `a-${Date.now()}`, role: "assistant", content: displayText }]);
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      setMessages((m) => [...m, { id: `a-${Date.now()}`, role: "assistant", content: `Error: ${msg}` }]);
    } finally {
      setIsGenerating(false);
    }
  }, [missingDetails, userId, planResult, setPlanResult, onPlanGenerated, setMessages, pendingFile, processFile]);

  const send = useCallback(async () => {
    const trimmed = input.trim();
    if (!trimmed || isGenerating) return;
    setInput("");
    await sendText(trimmed);
  }, [input, sendText, isGenerating]);

  const toggleVoice = useCallback(async () => {
    // Stop if already recording
    if (isListening) {
      mediaRecorderRef.current?.stop();
      return;
    }

    let stream: MediaStream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch {
      setMessages((m) => [
        ...m,
        {
          id: `a-${Date.now()}`,
          role: "assistant",
          content: "Microphone access denied. Please allow microphone access in your browser settings.",
        },
      ]);
      return;
    }

    const mimeType = getBestMimeType();
    const recorder = mimeType
      ? new MediaRecorder(stream, { mimeType })
      : new MediaRecorder(stream);

    const chunks: Blob[] = [];
    recorder.ondataavailable = (e) => {
      if (e.data.size > 0) chunks.push(e.data);
    };

    recorder.onstop = async () => {
      stream.getTracks().forEach((t) => t.stop());
      setIsListening(false);
      setVoiceStatus("processing");

      const blob = new Blob(chunks, { type: recorder.mimeType || mimeType || "audio/webm" });
      try {
        const transcript = await transcribeAudio(blob);
        setVoiceStatus("idle");
        if (transcript.trim()) {
          await sendText(transcript.trim());
        }
      } catch (e) {
        setVoiceStatus("idle");
        const msg = e instanceof Error ? e.message : String(e);
        setMessages((m) => [
          ...m,
          { id: `a-${Date.now()}`, role: "assistant", content: `Voice transcription failed: ${msg}` },
        ]);
      }
    };

    mediaRecorderRef.current = recorder;
    recorder.start();
    setIsListening(true);
    setVoiceStatus("recording");
  }, [isListening, sendText, setMessages]);

  const onFilePick = () => fileInputRef.current?.click();

  const onFileChange: ChangeEventHandler<HTMLInputElement> = (e) => {
    const f = e.target.files?.[0];
    e.target.value = "";
    if (!f) return;

    const name = f.name.toLowerCase();
    if (name.endsWith(".pdf")) {
      setMessages((m) => [
        ...m,
        { id: `a-${Date.now()}`, role: "assistant", content: "PDF analysis coming soon" },
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

    if (fileUploaded) {
      setPendingFile(f);
      setMessages((m) => [
        ...m,
        {
          id: `a-${Date.now()}`,
          role: "assistant",
          content: "You already have academic progress saved. Would you like to update it with the new file? Reply **yes** to update or **no** to keep the current one.",
        },
      ]);
    } else {
      void processFile(f);
    }
  };

  const micLabel =
    voiceStatus === "recording"
      ? "Tap to stop"
      : voiceStatus === "processing"
      ? "Transcribing…"
      : "Tap to speak";

  return (
    <aside className="flex w-[380px] shrink-0 flex-col border-l border-neutral-200 bg-[var(--scu-white)] shadow-sm">
      <div className="shrink-0 border-b border-neutral-200 px-4 py-3 flex items-center justify-between">
        <h2 className="text-sm font-semibold text-[var(--scu-text)]">SCU Course Planner</h2>
        {fileUploaded && (
          <span className="text-[10px] text-emerald-600 font-medium">● Progress loaded</span>
        )}
      </div>

      <div className="min-h-0 flex-1 space-y-3 overflow-y-auto px-4 py-4">
        {messages.map((msg) => (
          <div
            key={msg.id}
            className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}
          >
            <div
              className={`max-w-[90%] rounded-lg px-3 py-2 text-sm leading-relaxed whitespace-pre-wrap ${
                msg.role === "user"
                  ? "bg-neutral-100 text-[var(--scu-text)]"
                  : "bg-[var(--scu-gray)] text-[var(--scu-text)] ring-1 ring-neutral-200"
              }`}
            >
              {msg.content}
            </div>
          </div>
        ))}

        {/* Animated typing indicator while AI is generating */}
        {isGenerating && (
          <div className="flex justify-start">
            <div className="rounded-lg px-4 py-3 bg-[var(--scu-gray)] ring-1 ring-neutral-200 flex items-center gap-1.5">
              <span className="w-2 h-2 rounded-full bg-neutral-400 animate-bounce [animation-delay:0ms]" />
              <span className="w-2 h-2 rounded-full bg-neutral-400 animate-bounce [animation-delay:150ms]" />
              <span className="w-2 h-2 rounded-full bg-neutral-400 animate-bounce [animation-delay:300ms]" />
            </div>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      <div className="shrink-0 border-t border-neutral-200 p-3">
        <input
          ref={fileInputRef}
          type="file"
          accept=".pdf,.xlsx,.xlsm"
          className="hidden"
          onChange={onFileChange}
        />

        {/* Voice status bar */}
        {voiceStatus !== "idle" && (
          <div
            className={`mb-2 flex items-center gap-2 rounded-md px-3 py-2 text-xs font-medium ${
              voiceStatus === "recording"
                ? "bg-red-50 text-[var(--scu-red)]"
                : "bg-neutral-50 text-neutral-500"
            }`}
          >
            <span
              className={`inline-block h-2 w-2 rounded-full ${
                voiceStatus === "recording"
                  ? "bg-[var(--scu-red)] animate-pulse"
                  : "bg-neutral-400 animate-pulse"
              }`}
            />
            {voiceStatus === "recording"
              ? "Recording — tap mic to stop"
              : "Sending to AI for transcription…"}
          </div>
        )}

        <div className="flex items-end gap-2">
          <textarea
            ref={textareaRef}
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
              className="rounded-md p-2 text-neutral-500 hover:bg-neutral-100"
              title="Attach Excel file"
            >
              <PaperclipIcon />
            </button>
            <button
              type="button"
              onClick={() => void toggleVoice()}
              disabled={voiceStatus === "processing"}
              title={micLabel}
              className={`rounded-md p-2 transition ${
                voiceStatus === "recording"
                  ? "bg-[var(--scu-red)] text-white"
                  : voiceStatus === "processing"
                  ? "bg-neutral-100 text-neutral-400 cursor-wait"
                  : "text-neutral-500 hover:bg-neutral-100 hover:text-[var(--scu-text)]"
              }`}
            >
              {voiceStatus === "processing" ? <SpinnerIcon /> : <MicIcon />}
            </button>
          </div>
          <button
            type="button"
            onClick={() => void send()}
            disabled={isGenerating}
            className="h-[44px] shrink-0 rounded-md bg-[var(--scu-red)] px-4 text-sm font-semibold text-white shadow-sm transition hover:bg-[var(--scu-dark-red)] disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {isGenerating ? "…" : "Send"}
          </button>
        </div>
        <p className="mt-1.5 text-[10px] text-neutral-400">
          Voice works in all browsers — powered by Gemini transcription.
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

function SpinnerIcon() {
  return (
    <svg
      width="20"
      height="20"
      viewBox="0 0 24 24"
      fill="none"
      aria-hidden
      className="animate-spin"
    >
      <circle
        cx="12"
        cy="12"
        r="10"
        stroke="currentColor"
        strokeWidth="2"
        strokeDasharray="32"
        strokeDashoffset="12"
        strokeLinecap="round"
      />
    </svg>
  );
}
