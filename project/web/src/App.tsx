import { useCallback, useEffect, useMemo, useState } from "react";
import { getMemory, login as apiLogin } from "./api/client";
import { CalendarView } from "./components/CalendarView";
import { ChatPanel, type ChatUiMessage } from "./components/ChatPanel";
import { LeftPanel, type MemorySessionRow } from "./components/LeftPanel";
import { parseRecommendedFromMemoryContent } from "./utils/planCalendar";

const WELCOME_TEXT =
  "Upload your Academic Progress file or describe your preferences to get started.";

export default function App() {
  const [userId, setUserId] = useState<string | null>(null);
  const [missingDetails, setMissingDetails] = useState<unknown[]>([]);
  const [planResult, setPlanResult] = useState<Record<string, unknown> | null>(
    null,
  );
  const [messages, setMessages] = useState<ChatUiMessage[]>([
    { id: "m0", role: "assistant", content: WELCOME_TEXT },
  ]);
  const [memories, setMemories] = useState<Record<string, unknown>[]>([]);
  const [planSnapshots, setPlanSnapshots] = useState<
    {
      id: string;
      title: string;
      dateLabel: string;
      recommended: Record<string, unknown>[];
    }[]
  >([]);
  const [sessionCalendarRecommended, setSessionCalendarRecommended] =
    useState<Record<string, unknown>[] | null>(null);
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
  const [fileUploaded, setFileUploaded] = useState(false);

  useEffect(() => {
    if (!userId) {
      setMemories([]);
      return;
    }
    void getMemory(userId)
      .then((r) => {
        setMemories(Array.isArray(r.memories) ? r.memories : []);
      })
      .catch(() => setMemories([]));
  }, [userId]);

  const calendarRecommended = useMemo(() => {
    if (
      sessionCalendarRecommended !== null &&
      sessionCalendarRecommended.length > 0
    ) {
      return sessionCalendarRecommended;
    }
    const r = planResult?.recommended;
    if (Array.isArray(r) && r.length > 0) {
      return r as Record<string, unknown>[];
    }
    return null;
  }, [sessionCalendarRecommended, planResult]);

  const sessions: MemorySessionRow[] = useMemo(() => {
    const rows: MemorySessionRow[] = [];
    if (
      planResult &&
      Array.isArray(planResult.recommended) &&
      planResult.recommended.length > 0
    ) {
      rows.push({
        id: "current",
        title: "Current schedule",
        dateLabel: "From chat",
        kind: "current",
        recommended: planResult.recommended as Record<string, unknown>[],
      });
    }
    for (const snap of planSnapshots) {
      rows.push({
        id: snap.id,
        title: snap.title,
        dateLabel: snap.dateLabel,
        kind: "snapshot",
        recommended: snap.recommended,
      });
    }
    for (const m of memories) {
      const mid = m.id != null ? String(m.id) : "";
      rows.push({
        id: `mem-${mid}`,
        title: `${String(m.kind ?? "note")}: ${String(m.content ?? "").slice(0, 48)}`,
        dateLabel: String(m.created_at ?? ""),
        kind: "memory",
        memoryContent: String(m.content ?? ""),
      });
    }
    return rows;
  }, [planResult, planSnapshots, memories]);

  const handleLogin = useCallback(
    async (username: string, password: string) => {
      try {
        const r = await apiLogin(username, password);
        if (r.success && r.user_id) {
          setUserId(String(r.user_id));
          return { ok: true as const };
        }
        return { ok: false as const, error: "Invalid username or password." };
      } catch (e) {
        const hint =
          e instanceof Error ? e.message : "Could not reach the server.";
        const networkish =
          hint === "Failed to fetch" ||
          hint.includes("NetworkError") ||
          hint.includes("fetch resource");
        return {
          ok: false as const,
          error: networkish
            ? "Cannot reach API — start uvicorn on port 8000, restart `npm run dev` (Vite proxies /api), or check firewall."
            : hint,
        };
      }
    },
    [],
  );

  const handleSelectSession = useCallback((row: MemorySessionRow) => {
    setActiveSessionId(row.id);
    if (row.kind === "current") {
      setSessionCalendarRecommended(null);
      return;
    }
    if (row.kind === "snapshot") {
      setSessionCalendarRecommended(row.recommended ?? null);
      return;
    }
    if (row.memoryContent) {
      const parsed = parseRecommendedFromMemoryContent(row.memoryContent);
      setSessionCalendarRecommended(parsed);
    }
  }, []);

  const handlePlanGenerated = useCallback((plan: Record<string, unknown>) => {
    setSessionCalendarRecommended(null);
    setActiveSessionId("current");
    const recs = (plan.recommended as Record<string, unknown>[]) ?? [];
    if (recs.length > 0) {
      const d = new Date().toLocaleDateString();
      setPlanSnapshots((prev) => [
        {
          id: `snap-${Date.now()}`,
          title: `Plan · ${recs.length} courses`,
          dateLabel: d,
          recommended: recs,
        },
        ...prev,
      ]);
    }
  }, []);

  const handleNewPlan = useCallback(() => {
    setMissingDetails([]);
    setPlanResult(null);
    setPlanSnapshots([]);
    setSessionCalendarRecommended(null);
    setActiveSessionId(null);
    setFileUploaded(false);
    setMessages([{ id: "m0", role: "assistant", content: WELCOME_TEXT }]);
  }, []);

  return (
    <div className="flex h-screen w-screen overflow-hidden bg-[var(--scu-white)]">
      <LeftPanel
        userId={userId}
        onLogin={handleLogin}
        sessions={sessions}
        activeSessionId={activeSessionId}
        onSelectSession={handleSelectSession}
        onNewPlan={handleNewPlan}
      />
      <CalendarView recommendedCourses={calendarRecommended} />
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
      />
    </div>
  );
}
