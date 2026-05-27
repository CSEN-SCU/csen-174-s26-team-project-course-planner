import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type ChangeEventHandler,
  type Dispatch,
  type SetStateAction,
} from "react";
import {
  generatePlan,
  transcribeAudio,
  uploadTranscript,
  type MajorDetection,
} from "../api/client";
import type { ParsedRow } from "../types";
import { PlannerColumnHeader } from "./PlannerColumnHeader";
import { SignOutButton } from "./SignOutButton";

export type ChatUiMessage = {
  id: string;
  role: "user" | "assistant";
  content: string;
};

function completedCourseCodesFromRows(rows: ParsedRow[]): string[] {
  const codes = new Set<string>();
  for (const row of rows) {
    const status = (row.status ?? "").trim();
    if (status !== "Satisfied" && status !== "In Progress") continue;
    const code = (row.course_code ?? "").trim();
    if (code) codes.add(code);
  }
  return [...codes];
}

export type ChatPanelProps = {
  userId: string | null;
  parsedRows?: ParsedRow[];
  missingDetails: unknown[];
  planResult: Record<string, unknown> | null;
  messages: ChatUiMessage[];
  setMessages: Dispatch<SetStateAction<ChatUiMessage[]>>;
  setMissingDetails: (v: unknown[]) => void;
  setPlanResult: (v: Record<string, unknown> | null) => void;
  fileUploaded: boolean;
  setFileUploaded: (v: boolean) => void;
  onPlanGenerated: (plan: Record<string, unknown>, messages: ChatUiMessage[]) => void;
  prefillInput?: string | null;
  onPrefillConsumed?: () => void;
  /** Bump to focus the input without injecting text (e.g. on "New Plan"). */
  focusNonce?: number;
  setParsedRows?: (v: ParsedRow[]) => void;
  onSignOut?: () => void;
  studentMajorId?: string | null;
  majorConfirmed?: boolean;
  onTranscriptUploaded?: (detection: MajorDetection | null) => void;
};

function planSummaryText(plan: Record<string, unknown>): string {
  const recs = (plan.recommended as Record<string, unknown>[]) ?? [];
  const norm = (r: Record<string, unknown>) => String(r.course ?? "").trim().toUpperCase();
  const codeSet = new Set(recs.map(norm));
  const unitsOf = (r: Record<string, unknown>) => (r.units != null ? String(r.units) : "?");

  // A lab is grouped UNDER its lecture when that lecture is also in the plan
  // (SCU lecture+lab co-requisites are taken together — show them together).
  const isGroupedLab = (code: string) => /L$/.test(code) && codeSet.has(code.slice(0, -1));

  const lines: string[] = [];
  for (const r of recs) {
    const code = norm(r);
    if (isGroupedLab(code)) continue; // emitted beneath its lecture below
    lines.push(`• ${String(r.course ?? "?")} (${unitsOf(r)} units)`);
    const labCode = `${code}L`;
    if (codeSet.has(labCode)) {
      const lab = recs.find((x) => norm(x) === labCode);
      if (lab) lines.push(`   ↳ ${String(lab.course)} — lab (${unitsOf(lab)} units)`);
    }
  }

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
  parsedRows = [],
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
  focusNonce,
  setParsedRows,
  onSignOut,
  studentMajorId = null,
  majorConfirmed = false,
  onTranscriptUploaded,
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
  const dragCounterRef = useRef(0);
  const [isDragOver, setIsDragOver] = useState(false);

  const hasUserInput = messages.some((m) => m.role === "user");
  const canDropFiles = !hasUserInput;

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

  // Focus the input on demand (e.g. "New Plan") without injecting text.
  useEffect(() => {
    if (focusNonce && focusNonce > 0) {
      setTimeout(() => textareaRef.current?.focus(), 0);
    }
  }, [focusNonce]);

  const processFile = useCallback(async (f: File) => {
    try {
      const data = await uploadTranscript(f, userId ?? undefined);
      const md = (data.missing_details as unknown[]) ?? [];
      setMissingDetails(md);
      const pr = (data.parsed_rows as ParsedRow[]) ?? [];
      setParsedRows?.(pr);
      setFileUploaded(true);
      const det = (data.major_detection as MajorDetection | undefined) ?? null;
      onTranscriptUploaded?.(det);
      const majorHint = det?.message
        ? `\n\n${det.message}`
        : "";
      const reply = `Got it! Found ${md.length} missing requirements${userId ? " and saved your progress" : ""}.${majorHint} Confirm your major above, then tell me your preferences for next quarter.`;
      setMessages((m) => [...m, { id: `a-${Date.now()}`, role: "assistant", content: reply }]);
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      setMessages((m) => [...m, { id: `a-${Date.now()}`, role: "assistant", content: `Upload failed: ${msg}` }]);
    }
  }, [userId, setMissingDetails, setParsedRows, setFileUploaded, setMessages, onTranscriptUploaded]);

  const sendText = useCallback(async (text: string) => {
    const trimmed = text.trim();
    if (!trimmed) return;

    // Capture conversation state before this turn so we can save a full snapshot
    const userMsg: ChatUiMessage = { id: `u-${Date.now()}`, role: "user", content: trimmed };
    const preTurnMessages = messages;
    setMessages((m) => [...m, userMsg]);

    const lower = trimmed.toLowerCase();

    // Gate: must have Academic Progress export before planning
    if (!fileUploaded) {
      setMessages((m) => [
        ...m,
        {
          id: `a-${Date.now()}`,
          role: "assistant",
          content:
            "Please upload your Academic Progress Report (.xlsx) from Workday using the paperclip below.",
        },
      ]);
      return;
    }

    if (!majorConfirmed || !studentMajorId) {
      setMessages((m) => [
        ...m,
        {
          id: `a-${Date.now()}`,
          role: "assistant",
          content:
            "请先在上方的专业确认栏选择并确认你的专业（系统会根据 Academic Progress 推断，也可手动修改），然后再描述你想要的课表。",
        },
      ]);
      return;
    }

    // Handle pending Academic Progress update confirmation
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
        {
          parsed_rows: parsedRows,
          completed_course_codes: completedCourseCodesFromRows(parsedRows),
          student_major_id: studentMajorId ?? undefined,
        },
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

      const assistantMsg: ChatUiMessage = { id: `a-${Date.now()}`, role: "assistant", content: displayText };
      const fullConversation = [...preTurnMessages, userMsg, assistantMsg];
      onPlanGenerated(data, fullConversation);
      setMessages((m) => [...m, assistantMsg]);
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      setMessages((m) => [...m, { id: `a-${Date.now()}`, role: "assistant", content: `Error: ${msg}` }]);
    } finally {
      setIsGenerating(false);
    }
  }, [
    messages,
    missingDetails,
    userId,
    planResult,
    parsedRows,
    fileUploaded,
    setPlanResult,
    onPlanGenerated,
    setMessages,
    pendingFile,
    processFile,
  ]);

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

  const handleFile = useCallback(
    (f: File) => {
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
            content: "Please upload an Academic Progress export from Workday (.xlsx or .xlsm files).",
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
            content:
              "You already have academic progress saved. Would you like to update it with the new file? Reply **yes** to update or **no** to keep the current one.",
          },
        ]);
      } else {
        void processFile(f);
      }
    },
    [fileUploaded, processFile, setMessages],
  );

  const onFilePick = () => fileInputRef.current?.click();

  const onFileChange: ChangeEventHandler<HTMLInputElement> = (e) => {
    const f = e.target.files?.[0];
    e.target.value = "";
    if (f) handleFile(f);
  };

  const onDragEnter = useCallback(
    (e: React.DragEvent) => {
      if (!canDropFiles) return;
      e.preventDefault();
      dragCounterRef.current += 1;
      if (e.dataTransfer.types.includes("Files")) setIsDragOver(true);
    },
    [canDropFiles],
  );

  const onDragOver = useCallback(
    (e: React.DragEvent) => {
      if (!canDropFiles) return;
      e.preventDefault();
      e.dataTransfer.dropEffect = "copy";
    },
    [canDropFiles],
  );

  const onDragLeave = useCallback(
    (e: React.DragEvent) => {
      if (!canDropFiles) return;
      e.preventDefault();
      dragCounterRef.current -= 1;
      if (dragCounterRef.current <= 0) {
        dragCounterRef.current = 0;
        setIsDragOver(false);
      }
    },
    [canDropFiles],
  );

  const onDrop = useCallback(
    (e: React.DragEvent) => {
      if (!canDropFiles) return;
      e.preventDefault();
      dragCounterRef.current = 0;
      setIsDragOver(false);
      const f = e.dataTransfer.files?.[0];
      if (f) handleFile(f);
    },
    [canDropFiles, handleFile],
  );

  const micLabel =
    voiceStatus === "recording"
      ? "Tap to stop"
      : voiceStatus === "processing"
      ? "Transcribing…"
      : "Tap to speak";
  const uploadHelperText = fileUploaded
    ? "Academic Progress is saved. Use the paperclip if you want to update it."
    : canDropFiles
    ? "Drag and drop your Academic Progress (.xlsx or .xlsm files) here, or use the paperclip to upload."
    : "Upload your Academic Progress (.xlsx) file with the paperclip.";

  return (
    <aside
      className="relative grid h-full min-h-0 min-w-0 grid-rows-[auto_minmax(0,1fr)_auto] overflow-hidden border-l border-neutral-200 bg-[var(--scu-white)] shadow-sm"
      onDragEnter={onDragEnter}
      onDragOver={onDragOver}
      onDragLeave={onDragLeave}
      onDrop={onDrop}
    >
      <PlannerColumnHeader align="end">
        {onSignOut ? <SignOutButton onClick={onSignOut} /> : null}
      </PlannerColumnHeader>

      {isDragOver && canDropFiles && (
        <div
          className="pointer-events-none absolute inset-0 z-10 flex flex-col items-center justify-center gap-2 bg-white/90 px-6 text-center ring-2 ring-inset ring-[var(--scu-red)]"
          aria-hidden
        >
          <PaperclipIcon />
          <p className="text-sm font-semibold text-[var(--scu-text)]">Drop your Academic Progress file</p>
          <p className="text-xs text-neutral-500">.xlsx or .xlsm export from Workday</p>
        </div>
      )}

      <div className="relative min-h-0 space-y-3 overflow-y-auto px-4 py-4">
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

        <div className="flex items-stretch gap-2">
          <textarea
            ref={textareaRef}
            rows={1}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                void send();
              }
            }}
            placeholder="Message…"
            className="min-h-0 flex-1 resize-none self-stretch rounded-md border border-neutral-300 px-3 py-2 text-sm text-[var(--scu-text)] outline-none ring-0 placeholder:text-neutral-400 focus:border-[var(--scu-red)] focus:ring-1 focus:ring-[var(--scu-red)]"
          />
          <div className="flex shrink-0 flex-col items-center justify-between gap-1">
            <button
              type="button"
              onClick={onFilePick}
              className="rounded-md p-2 text-neutral-500 hover:bg-neutral-100"
              title={fileUploaded ? "Update Academic Progress" : "Upload Academic Progress"}
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
                  ? "cursor-wait bg-neutral-100 text-neutral-400"
                  : "text-neutral-500 hover:bg-neutral-100 hover:text-[var(--scu-text)]"
              }`}
            >
              {voiceStatus === "processing" ? <SpinnerIcon /> : <MicIcon />}
            </button>
            <button
              type="button"
              onClick={() => void send()}
              disabled={isGenerating}
              className="rounded-md bg-[var(--scu-red)] px-3 py-1.5 text-sm font-semibold text-white shadow-sm transition hover:bg-[var(--scu-dark-red)] disabled:cursor-not-allowed disabled:opacity-50"
            >
              {isGenerating ? "…" : "Send"}
            </button>
          </div>
        </div>
        <p className="mt-1.5 text-[10px] text-neutral-400">
          {uploadHelperText}
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
