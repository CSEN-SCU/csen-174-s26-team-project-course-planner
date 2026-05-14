import { useCallback, useEffect, useMemo, useState } from "react";
import { deleteMemory, exchangeGoogleOauth, generateFourYearPlan, getMemory, login as apiLogin, register as apiRegister, saveMemory } from "./api/client";
import { CalendarView } from "./components/CalendarView";
import { ChatPanel, type ChatUiMessage } from "./components/ChatPanel";
import { FourYearPlanView } from "./components/FourYearPlanView";
import { LeftPanel, type MemorySessionRow } from "./components/LeftPanel";
import type { FourYearPlan, ParsedRow } from "./types";
import { CALENDAR_START_HOUR, WEEKDAY_LABELS } from "./types";

const WELCOME_TEXT =
  "Upload your Academic Progress file or describe your preferences to get started.";

export default function App() {
  const [userId, setUserId] = useState<string | null>(null);
  const [missingDetails, setMissingDetails] = useState<unknown[]>([]);
  const [planResult, setPlanResult] = useState<Record<string, unknown> | null>(null);
  const [messages, setMessages] = useState<ChatUiMessage[]>([
    { id: "m0", role: "assistant", content: WELCOME_TEXT },
  ]);
  const [planSnapshots, setPlanSnapshots] = useState<
    {
      id: string;
      memoryId?: number;
      title: string;
      dateLabel: string;
      recommended: Record<string, unknown>[];
      messages?: ChatUiMessage[];
      fourYearPlan?: FourYearPlan | null;
    }[]
  >([]);
  const [sessionCalendarRecommended, setSessionCalendarRecommended] =
    useState<Record<string, unknown>[] | null>(null);
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
  const [fileUploaded, setFileUploaded] = useState(false);
  const [localOverride, setLocalOverride] = useState<Record<string, unknown>[] | null>(null);
  const [chatPrefill, setChatPrefill] = useState<string | null>(null);
  const [viewMode, setViewMode] = useState<"calendar" | "four-year">("calendar");
  const [fourYearPlan, setFourYearPlan] = useState<FourYearPlan | null>(null);
  const [fourYearGenerating, setFourYearGenerating] = useState(false);
  const [parsedRows, setParsedRows] = useState<ParsedRow[]>([]);
  const [googleAuthError, setGoogleAuthError] = useState<string | null>(null);

  // Consume Google OAuth handoff token on first load (single-use).
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const token = params.get("google_oauth");
    const err = params.get("google_oauth_error");

    if (!token && !err) return;

    // Always clear the URL so a reload doesn't replay the handoff.
    params.delete("google_oauth");
    params.delete("google_oauth_error");
    const q = params.toString();
    window.history.replaceState({}, document.title, q ? `?${q}` : window.location.pathname);

    if (err) {
      setGoogleAuthError(
        err === "access_denied" ? "Google sign-in was cancelled." : "Google sign-in failed.",
      );
      return;
    }
    if (!token) return;
    void exchangeGoogleOauth(token)
      .then((r) => {
        if (r.success && r.user_id) {
          setUserId(String(r.user_id));
          setGoogleAuthError(null);
        } else {
          setGoogleAuthError("Google sign-in failed. Please try again.");
        }
      })
      .catch(() => {
        setGoogleAuthError("Google sign-in failed. Please try again.");
      });
  }, []);

  // Load academic progress + past plan snapshots on login
  useEffect(() => {
    if (!userId) {
      setMissingDetails([]);
      setFileUploaded(false);
      setPlanSnapshots([]);
      setParsedRows([]);
      return;
    }
    void getMemory(userId)
      .then((r) => {
        const mems: Record<string, unknown>[] = Array.isArray(r.memories) ? r.memories : [];

        // Restore academic progress
        const progressItems = mems
          .filter((m) => m.kind === "academic_progress")
          .sort((a, b) => String(b.created_at ?? "").localeCompare(String(a.created_at ?? "")));
        if (progressItems.length > 0) {
          try {
            const details = JSON.parse(String(progressItems[0].content ?? "[]")) as unknown[];
            if (Array.isArray(details) && details.length > 0) {
              setMissingDetails(details);
              setFileUploaded(true);
            }
          } catch { /* ignore */ }
        }

        // Restore parsed transcript rows (full course history for the 4-year plan)
        const parsedRowItems = mems
          .filter((m) => m.kind === "parsed_rows")
          .sort((a, b) => String(b.created_at ?? "").localeCompare(String(a.created_at ?? "")));
        if (parsedRowItems.length > 0) {
          try {
            const rows = JSON.parse(String(parsedRowItems[0].content ?? "[]")) as ParsedRow[];
            if (Array.isArray(rows) && rows.length > 0) {
              setParsedRows(rows);
            }
          } catch { /* ignore */ }
        }

        // Restore past plan snapshots
        const planMems = mems
          .filter((m) => m.kind === "plan_outcome")
          .sort((a, b) => String(b.created_at ?? "").localeCompare(String(a.created_at ?? "")));
        const loadedSnaps = planMems.flatMap((m) => {
          try {
            const data = JSON.parse(String(m.content ?? "")) as {
              recommended?: unknown; title?: string; dateLabel?: string; messages?: unknown;
              fourYearPlan?: unknown;
            };
            if (Array.isArray(data.recommended) && data.recommended.length > 0) {
              return [{
                id: `mem-snap-${String(m.id ?? Date.now())}`,
                memoryId: typeof m.id === "number" ? m.id : undefined,
                title: data.title ?? "Past plan",
                dateLabel: data.dateLabel ?? String(m.created_at ?? ""),
                recommended: data.recommended as Record<string, unknown>[],
                messages: Array.isArray(data.messages) ? data.messages as ChatUiMessage[] : undefined,
                fourYearPlan: (data.fourYearPlan as FourYearPlan | undefined) ?? null,
              }];
            }
          } catch { /* ignore */ }
          return [];
        });
        setPlanSnapshots(loadedSnaps);
      })
      .catch(() => { /* ignore */ });
  }, [userId]);

  // Base calendar data from current session or plan result
  const calendarRecommended = useMemo(() => {
    if (sessionCalendarRecommended !== null && sessionCalendarRecommended.length > 0) {
      return sessionCalendarRecommended;
    }
    const r = planResult?.recommended;
    if (Array.isArray(r) && r.length > 0) return r as Record<string, unknown>[];
    return null;
  }, [sessionCalendarRecommended, planResult]);

  // Effective courses shown = local overrides (user edits) on top of base
  const effectiveRecommended = useMemo(
    () => localOverride ?? calendarRecommended,
    [localOverride, calendarRecommended],
  );

  // Each conversation = one snapshot row. The most recent snapshot IS the
  // "current" conversation when active — no separate pseudo-row needed.
  const sessions: MemorySessionRow[] = useMemo(() => {
    return planSnapshots.map((snap) => ({
      id: snap.id,
      title: snap.title,
      dateLabel: snap.dateLabel,
      kind: "snapshot" as const,
      recommended: snap.recommended,
      messages: snap.messages,
    }));
  }, [planSnapshots]);

  const handleLogin = useCallback(async (username: string, password: string) => {
    try {
      const r = await apiLogin(username, password);
      if (r.success && r.user_id) {
        setUserId(String(r.user_id));
        return { ok: true as const };
      }
      return { ok: false as const, error: "Invalid username or password." };
    } catch (e) {
      const hint = e instanceof Error ? e.message : "Could not reach the server.";
      const networkish = hint === "Failed to fetch" || hint.includes("NetworkError") || hint.includes("fetch resource");
      return {
        ok: false as const,
        error: networkish
          ? "Cannot reach API — start uvicorn on port 8000, restart `npm run dev`, or check firewall."
          : hint,
      };
    }
  }, []);

  const handleRegister = useCallback(async (username: string, password: string) => {
    try {
      const r = await apiRegister(username, password);
      if (!r.success) return { ok: false as const, error: "Username already taken." };
      // Auto-login after successful registration
      return await handleLogin(username, password);
    } catch (e) {
      const hint = e instanceof Error ? e.message : "Could not reach the server.";
      const networkish = hint === "Failed to fetch" || hint.includes("NetworkError") || hint.includes("fetch resource");
      return {
        ok: false as const,
        error: networkish
          ? "Cannot reach API — start uvicorn on port 8000, restart `npm run dev`, or check firewall."
          : hint,
      };
    }
  }, [handleLogin]);

  const handleSelectSession = useCallback((row: MemorySessionRow) => {
    setLocalOverride(null);
    setActiveSessionId(row.id);
    setSessionCalendarRecommended(row.recommended ?? null);
    // Mirror the snapshot into planResult so chat follow-ups treat it as
    // the previous_plan baseline rather than appending to a stale conversation.
    setPlanResult({ recommended: row.recommended ?? [] });
    const snap = planSnapshots.find((s) => s.id === row.id);
    setFourYearPlan(snap?.fourYearPlan ?? null);
    if (row.messages && row.messages.length > 0) {
      setMessages(row.messages as ChatUiMessage[]);
    } else {
      setMessages([{ id: "m-restore", role: "assistant", content: "Viewing a past session. The calendar shows courses from this plan." }]);
    }
  }, [setMessages, planSnapshots]);

  const handlePlanGenerated = useCallback((plan: Record<string, unknown>, msgs: ChatUiMessage[]) => {
    setLocalOverride(null);
    setSessionCalendarRecommended(null);
    const recs = (plan.recommended as Record<string, unknown>[]) ?? [];
    if (recs.length === 0) return;

    const d = new Date().toLocaleDateString();
    const title = `Plan · ${recs.length} courses`;

    // If there's an active conversation, UPDATE that snapshot in place
    // (same conversation, multiple turns). Otherwise CREATE a new one.
    const existing = activeSessionId
      ? planSnapshots.find((s) => s.id === activeSessionId)
      : null;

    if (existing) {
      const updated = {
        ...existing,
        title,
        dateLabel: d,
        recommended: recs,
        messages: msgs,
      };
      setPlanSnapshots((prev) =>
        prev.map((s) => (s.id === existing.id ? updated : s)),
      );

      if (userId && existing.memoryId != null) {
        // Replace the memory row so storage matches state
        void deleteMemory(userId, existing.memoryId).catch(() => {});
        void saveMemory(
          userId,
          "plan_outcome",
          JSON.stringify({
            recommended: recs,
            title,
            dateLabel: d,
            messages: msgs,
            fourYearPlan: existing.fourYearPlan ?? null,
          }),
        )
          .then((r) => {
            const newId = typeof r?.id === "number" ? r.id : undefined;
            setPlanSnapshots((prev) =>
              prev.map((s) =>
                s.id === existing.id ? { ...s, memoryId: newId } : s,
              ),
            );
          })
          .catch(() => {});
      }
    } else {
      const snapId = `snap-${Date.now()}`;
      setActiveSessionId(snapId);
      setPlanSnapshots((prev) => [
        { id: snapId, title, dateLabel: d, recommended: recs, messages: msgs },
        ...prev,
      ]);
      if (userId) {
        void saveMemory(
          userId,
          "plan_outcome",
          JSON.stringify({ recommended: recs, title, dateLabel: d, messages: msgs }),
        )
          .then((r) => {
            const memoryId = typeof r?.id === "number" ? r.id : undefined;
            setPlanSnapshots((prev) =>
              prev.map((s) => (s.id === snapId ? { ...s, memoryId } : s)),
            );
          })
          .catch(() => {});
      }
    }
  }, [userId, activeSessionId, planSnapshots]);

  const handleNewPlan = useCallback(() => {
    // Keep missingDetails, fileUploaded, planSnapshots — only reset current chat
    setLocalOverride(null);
    setPlanResult(null);
    setSessionCalendarRecommended(null);
    setFourYearPlan(null);
    setActiveSessionId(null);
    setMessages([{ id: "m0", role: "assistant", content: WELCOME_TEXT }]);
  }, []);

  const handleDeleteSession = useCallback((id: string) => {
    const snap = planSnapshots.find((s) => s.id === id);
    setPlanSnapshots((prev) => prev.filter((s) => s.id !== id));
    if (activeSessionId === id) {
      setActiveSessionId(null);
      setSessionCalendarRecommended(null);
      setMessages([{ id: "m0", role: "assistant", content: WELCOME_TEXT }]);
    }
    if (userId && snap?.memoryId != null) {
      void deleteMemory(userId, snap.memoryId).catch(() => { /* non-fatal */ });
    }
  }, [planSnapshots, activeSessionId, userId, setMessages]);

  const handleRemoveCourse = useCallback((idx: number) => {
    const base = localOverride ?? calendarRecommended ?? [];
    setLocalOverride(base.filter((_, i) => i !== idx));
  }, [localOverride, calendarRecommended]);

  const handleGenerateFourYearPlan = useCallback(async () => {
    if (!missingDetails.length || fourYearGenerating) return;
    setFourYearGenerating(true);
    try {
      const result = await generateFourYearPlan(
        missingDetails,
        userId ?? "anonymous",
      );
      const plan = result as FourYearPlan;
      setFourYearPlan(plan);

      // Attach the new 4-year plan to the active conversation. If no
      // conversation is active yet, fall back to the most recent snapshot.
      const targetSnap = activeSessionId
        ? planSnapshots.find((s) => s.id === activeSessionId)
        : planSnapshots[0];

      if (targetSnap && userId) {
        const updated = { ...targetSnap, fourYearPlan: plan };
        setPlanSnapshots((prev) =>
          prev.map((s) => (s.id === targetSnap.id ? updated : s)),
        );

        // Replace the old memory entry with one that includes fourYearPlan
        if (targetSnap.memoryId != null) {
          await deleteMemory(userId, targetSnap.memoryId).catch(() => {
            /* non-fatal */
          });
        }
        void saveMemory(
          userId,
          "plan_outcome",
          JSON.stringify({
            recommended: targetSnap.recommended,
            title: targetSnap.title,
            dateLabel: targetSnap.dateLabel,
            messages: targetSnap.messages,
            fourYearPlan: plan,
          }),
        )
          .then((r) => {
            const newId = typeof r?.id === "number" ? r.id : undefined;
            setPlanSnapshots((prev) =>
              prev.map((s) =>
                s.id === targetSnap.id ? { ...s, memoryId: newId } : s,
              ),
            );
          })
          .catch(() => {
            /* non-fatal */
          });
      }
    } catch (e) {
      console.error("Four-year plan generation failed:", e);
    } finally {
      setFourYearGenerating(false);
    }
  }, [missingDetails, userId, fourYearGenerating, activeSessionId, planSnapshots]);

  const handleSlotClick = useCallback((dayIndex: number, slotIndex: number) => {
    const dayName = WEEKDAY_LABELS[dayIndex] ?? "Monday";
    const totalMin = CALENDAR_START_HOUR * 60 + slotIndex * 30;
    const d = new Date();
    d.setHours(Math.floor(totalMin / 60), totalMin % 60, 0, 0);
    const timeStr = d.toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit", hour12: true });
    setChatPrefill(`Can you add a course for me on ${dayName} around ${timeStr}?`);
  }, []);

  return (
    <div className="flex h-screen w-screen overflow-hidden bg-[var(--scu-white)]">
      <LeftPanel
        userId={userId}
        onLogin={handleLogin}
        onRegister={handleRegister}
        sessions={sessions}
        activeSessionId={activeSessionId}
        onSelectSession={handleSelectSession}
        onDeleteSession={handleDeleteSession}
        onNewPlan={handleNewPlan}
        externalAuthError={googleAuthError}
      />

      {/* Main view area with tab toggle */}
      <div className="flex min-h-0 min-w-0 flex-1 flex-col">
        {/* Tab bar */}
        <div className="flex shrink-0 border-b border-neutral-200 bg-white px-3 pt-1">
          <button
            className={`px-4 py-2 text-xs font-semibold border-b-2 transition ${
              viewMode === "calendar"
                ? "border-[var(--scu-red)] text-[var(--scu-red)]"
                : "border-transparent text-neutral-400 hover:text-neutral-600"
            }`}
            onClick={() => setViewMode("calendar")}
          >
            This Quarter
          </button>
          <button
            className={`px-4 py-2 text-xs font-semibold border-b-2 transition ${
              viewMode === "four-year"
                ? "border-[var(--scu-red)] text-[var(--scu-red)]"
                : "border-transparent text-neutral-400 hover:text-neutral-600"
            }`}
            onClick={() => setViewMode("four-year")}
          >
            4-Year Plan
          </button>
        </div>

        {viewMode === "calendar" ? (
          <CalendarView
            recommendedCourses={effectiveRecommended}
            onRemoveCourse={handleRemoveCourse}
            onSlotClick={handleSlotClick}
          />
        ) : (
          <FourYearPlanView
            plan={fourYearPlan}
            isGenerating={fourYearGenerating}
            hasTranscript={fileUploaded}
            onGenerate={handleGenerateFourYearPlan}
            parsedRows={parsedRows}
          />
        )}
      </div>

      <ChatPanel
        userId={userId}
        missingDetails={missingDetails}
        planResult={planResult}
        messages={messages}
        setMessages={setMessages}
        setMissingDetails={setMissingDetails}
        setPlanResult={setPlanResult}
        fileUploaded={fileUploaded}
        setFileUploaded={setFileUploaded}
        onPlanGenerated={handlePlanGenerated}
        prefillInput={chatPrefill}
        onPrefillConsumed={() => setChatPrefill(null)}
        setParsedRows={setParsedRows}
      />
    </div>
  );
}
