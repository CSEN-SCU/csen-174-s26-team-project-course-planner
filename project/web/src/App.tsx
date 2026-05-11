import { useCallback, useEffect, useMemo, useState } from "react";
import { deleteMemory, getMemory, login as apiLogin, saveMemory } from "./api/client";
import { CalendarView } from "./components/CalendarView";
import { ChatPanel, type ChatUiMessage } from "./components/ChatPanel";
import { LeftPanel, type MemorySessionRow } from "./components/LeftPanel";
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
    { id: string; memoryId?: number; title: string; dateLabel: string; recommended: Record<string, unknown>[]; messages?: ChatUiMessage[] }[]
  >([]);
  const [sessionCalendarRecommended, setSessionCalendarRecommended] =
    useState<Record<string, unknown>[] | null>(null);
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
  const [fileUploaded, setFileUploaded] = useState(false);
  const [localOverride, setLocalOverride] = useState<Record<string, unknown>[] | null>(null);
  const [chatPrefill, setChatPrefill] = useState<string | null>(null);

  // Load academic progress + past plan snapshots on login
  useEffect(() => {
    if (!userId) {
      setMissingDetails([]);
      setFileUploaded(false);
      setPlanSnapshots([]);
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

        // Restore past plan snapshots
        const planMems = mems
          .filter((m) => m.kind === "plan_outcome")
          .sort((a, b) => String(b.created_at ?? "").localeCompare(String(a.created_at ?? "")));
        const loadedSnaps = planMems.flatMap((m) => {
          try {
            const data = JSON.parse(String(m.content ?? "")) as {
              recommended?: unknown; title?: string; dateLabel?: string; messages?: unknown;
            };
            if (Array.isArray(data.recommended) && data.recommended.length > 0) {
              return [{
                id: `mem-snap-${String(m.id ?? Date.now())}`,
                memoryId: typeof m.id === "number" ? m.id : undefined,
                title: data.title ?? "Past plan",
                dateLabel: data.dateLabel ?? String(m.created_at ?? ""),
                recommended: data.recommended as Record<string, unknown>[],
                messages: Array.isArray(data.messages) ? data.messages as ChatUiMessage[] : undefined,
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

  const sessions: MemorySessionRow[] = useMemo(() => {
    const rows: MemorySessionRow[] = [];
    if (planResult && Array.isArray(planResult.recommended) && planResult.recommended.length > 0) {
      rows.push({
        id: "current",
        title: "Current schedule",
        dateLabel: "From chat",
        kind: "current",
        recommended: planResult.recommended as Record<string, unknown>[],
      });
    }
    for (const snap of planSnapshots) {
      rows.push({ id: snap.id, title: snap.title, dateLabel: snap.dateLabel, kind: "snapshot", recommended: snap.recommended, messages: snap.messages });
    }
    return rows;
  }, [planResult, planSnapshots]);

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

  const handleSelectSession = useCallback((row: MemorySessionRow) => {
    setLocalOverride(null);
    setActiveSessionId(row.id);
    if (row.kind === "current") {
      setSessionCalendarRecommended(null);
    } else if (row.kind === "snapshot") {
      setSessionCalendarRecommended(row.recommended ?? null);
      if (row.messages && row.messages.length > 0) {
        setMessages(row.messages as ChatUiMessage[]);
      } else {
        setMessages([{ id: "m-restore", role: "assistant", content: "Viewing a past session. The calendar shows courses from this plan." }]);
      }
    }
  }, [setMessages]);

  const handlePlanGenerated = useCallback((plan: Record<string, unknown>, msgs: ChatUiMessage[]) => {
    setLocalOverride(null);
    setSessionCalendarRecommended(null);
    setActiveSessionId("current");
    const recs = (plan.recommended as Record<string, unknown>[]) ?? [];
    if (recs.length > 0) {
      const d = new Date().toLocaleDateString();
      const title = `Plan · ${recs.length} courses`;
      const snapId = `snap-${Date.now()}`;
      if (userId) {
        void saveMemory(userId, "plan_outcome", JSON.stringify({ recommended: recs, title, dateLabel: d, messages: msgs }))
          .then((r) => {
            const memoryId = typeof r?.id === "number" ? r.id : undefined;
            setPlanSnapshots((prev) => [{ id: snapId, memoryId, title, dateLabel: d, recommended: recs, messages: msgs }, ...prev]);
          })
          .catch(() => {
            setPlanSnapshots((prev) => [{ id: snapId, title, dateLabel: d, recommended: recs, messages: msgs }, ...prev]);
          });
      } else {
        setPlanSnapshots((prev) => [{ id: snapId, title, dateLabel: d, recommended: recs, messages: msgs }, ...prev]);
      }
    }
  }, [userId]);

  const handleNewPlan = useCallback(() => {
    // Keep missingDetails, fileUploaded, planSnapshots — only reset current chat
    setLocalOverride(null);
    setPlanResult(null);
    setSessionCalendarRecommended(null);
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
        sessions={sessions}
        activeSessionId={activeSessionId}
        onSelectSession={handleSelectSession}
        onDeleteSession={handleDeleteSession}
        onNewPlan={handleNewPlan}
      />
      <CalendarView
        recommendedCourses={effectiveRecommended}
        onRemoveCourse={handleRemoveCourse}
        onSlotClick={handleSlotClick}
      />
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
      />
    </div>
  );
}
