import { useCallback, useEffect, useMemo, useState } from "react";
import {
  deleteAllUserData,
  deleteMemory,
  generateFourYearPlan,
  getMemory,
  saveMemory,
  type OfferedCourse,
} from "./api/client";
import { AddCoursePicker } from "./components/AddCoursePicker";
import { CalendarView } from "./components/CalendarView";
import { ChatPanel, type ChatUiMessage } from "./components/ChatPanel";
import { FourYearPlanView } from "./components/FourYearPlanView";
import { LeftPanel, type MemorySessionRow } from "./components/LeftPanel";
import type { FourYearPlan, ParsedRow } from "./types";
import { DeleteUserDataConfirm } from "./components/DeleteUserDataConfirm";
import { FirstLoginCarousel } from "./components/FirstLoginCarousel";
import { SlotSuggestionPopover } from "./components/SlotSuggestionPopover";
import { clearLocalSession } from "./auth/session";
import { SiteFooter } from "./components/SiteFooter";
import { CALENDAR_START_HOUR } from "./types";

const WELCOME_TEXT =
  "Upload your Academic Progress file or describe your preferences to get started.";
const NEW_PLAN_TEXT =
  "Started a new plan. Upload your Academic Progress file or describe your preferences for next quarter.";
const INTRO_SEEN_KEY_PREFIX = "scu_planner_intro_seen:";

export type AppProps = {
  userId: string;
  onSignOut: () => void;
};

export default function App({ userId, onSignOut }: AppProps) {
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
  // Bumped to ask the chat panel to focus its input (e.g. on "New Plan"),
  // without injecting any text into the box.
  const [chatFocusNonce, setChatFocusNonce] = useState(0);
  const [viewMode, setViewMode] = useState<"calendar" | "four-year">("calendar");
  const [fourYearPlan, setFourYearPlan] = useState<FourYearPlan | null>(null);
  const [fourYearGenerating, setFourYearGenerating] = useState(false);
  const [parsedRows, setParsedRows] = useState<ParsedRow[]>([]);
  const [deleteDataOpen, setDeleteDataOpen] = useState(false);
  const [deleteDataBusy, setDeleteDataBusy] = useState(false);
  const [deleteDataNotice, setDeleteDataNotice] = useState<string | null>(null);
  const [firstLoginCarouselOpen, setFirstLoginCarouselOpen] = useState(false);
  // Slot suggestion popover state (R6)
  const [slotPopoverOpen, setSlotPopoverOpen] = useState(false);
  const [slotPopoverData, setSlotPopoverData] = useState<{
    dayIndex: number;
    slotIndex: number;
    startMin: number;
    endMin: number;
    clientX: number;
    clientY: number;
  } | null>(null);

  // Load academic progress + past plan snapshots for this user
  useEffect(() => {
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

  useEffect(() => {
    setFirstLoginCarouselOpen(!hasSeenFirstLoginCarousel(userId));
  }, [userId]);

  useEffect(() => {
    const url = new URL(window.location.href);
    if (url.searchParams.get("delete-user-data") !== "1") return;

    setDeleteDataOpen(true);
    url.searchParams.delete("delete-user-data");
    window.history.replaceState({}, "", `${url.pathname}${url.search}${url.hash}`);
  }, []);

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
    // Keep missingDetails, fileUploaded, parsedRows, planSnapshots — only reset current chat.
    setLocalOverride(null);
    setPlanResult(null);
    setSessionCalendarRecommended(null);
    setFourYearPlan(null);
    setFourYearGenerating(false);
    setActiveSessionId(null);
    // Close any open slot-suggestion popover so it doesn't linger across plans.
    setSlotPopoverOpen(false);
    setSlotPopoverData(null);
    // Always give visible feedback, even from an already-empty state:
    // distinct message, switch to the calendar tab, and focus the chat input.
    setMessages([{ id: `m-new-${Date.now()}`, role: "assistant", content: NEW_PLAN_TEXT }]);
    setViewMode("calendar");
    setChatFocusNonce((n) => n + 1);
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

  // Manual "+ Add course": append picked courses (+ lab co-requisite) to the
  // live edit layer so they land on the calendar immediately — no AI call.
  const handleAddCourses = useCallback((picked: OfferedCourse[]) => {
    const base = localOverride ?? calendarRecommended ?? [];
    const present = new Set(
      base.map((r) => String((r as { course?: unknown }).course ?? "").trim().toUpperCase()),
    );
    const additions = picked
      .filter((c) => !present.has(c.course.trim().toUpperCase()))
      .map((c) => ({
        course: c.course,
        title: c.title ?? undefined,
        units: c.units ?? undefined,
        best_professor: c.professor ?? undefined,
        meeting_days: c.meeting_days,
        meeting_start_min: c.meeting_start_min,
        meeting_end_min: c.meeting_end_min,
        category: "Manually added",
        reason: "Added manually",
        _manualAdd: true,
      }));
    if (additions.length === 0) return;
    setLocalOverride([...base, ...additions]);
  }, [localOverride, calendarRecommended]);

  // Add course from slot suggestion popover (R6)
  const handleAddFromSlotSuggestion = useCallback((course: Record<string, unknown>) => {
    const base = localOverride ?? calendarRecommended ?? [];
    const courseCode = String(course.course ?? "").trim().toUpperCase();
    const present = new Set(
      base.map((r) => String((r as { course?: unknown }).course ?? "").trim().toUpperCase()),
    );
    if (present.has(courseCode)) return;
    setLocalOverride([...base, { ...course, _slotSuggestion: true }]);
  }, [localOverride, calendarRecommended]);

  const effectiveCodes = useMemo(
    () =>
      (effectiveRecommended ?? []).map((r) =>
        String((r as { course?: unknown }).course ?? ""),
      ),
    [effectiveRecommended],
  );

  const handleGenerateFourYearPlan = useCallback(async (preferences: string) => {
    if (!missingDetails.length || fourYearGenerating) return;
    setFourYearGenerating(true);
    try {
      const result = await generateFourYearPlan(
        missingDetails,
        userId ?? "anonymous",
        preferences.trim() || undefined,
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

  const resetLocalPlannerState = useCallback(() => {
    clearLocalSession();
    onSignOut();
    setMissingDetails([]);
    setPlanResult(null);
    setMessages([{ id: "m0", role: "assistant", content: WELCOME_TEXT }]);
    setPlanSnapshots([]);
    setSessionCalendarRecommended(null);
    setActiveSessionId(null);
    setFileUploaded(false);
    setLocalOverride(null);
    setChatPrefill(null);
    setViewMode("calendar");
    setFourYearPlan(null);
    setFourYearGenerating(false);
    setParsedRows([]);
  }, [onSignOut]);

  const finishDeleteUserData = useCallback(
    (serverNotice: string | null) => {
      setDeleteDataOpen(false);
      setDeleteDataBusy(false);
      setDeleteDataNotice(null);
      resetLocalPlannerState();
      if (serverNotice) {
        try {
          sessionStorage.setItem("scu_delete_user_data_notice", serverNotice);
        } catch {
          /* ignore */
        }
      }
      window.location.href = "/";
    },
    [resetLocalPlannerState],
  );

  const handleConfirmDeleteUserData = useCallback(async () => {
    setDeleteDataBusy(true);
    setDeleteDataNotice(null);
    let serverNotice: string | null = null;
    try {
      await deleteAllUserData(userId);
    } catch (e) {
      const hint = e instanceof Error ? e.message : "Could not reach the server.";
      serverNotice =
        "Signed out on this device. Server data could not be cleared (" +
        hint +
        ") — upload Academic Progress again after your next sign-in.";
    }
    finishDeleteUserData(serverNotice);
  }, [userId, finishDeleteUserData]);

  const handleCancelDeleteUserData = useCallback(() => {
    if (deleteDataBusy) return;
    setDeleteDataOpen(false);
    setDeleteDataNotice(null);
  }, [deleteDataBusy]);

  const handleFinishFirstLoginCarousel = useCallback(() => {
    markFirstLoginCarouselSeen(userId);
    setFirstLoginCarouselOpen(false);
  }, [userId]);

  const handleSlotClick = useCallback((dayIndex: number, slotIndex: number, clientX: number, clientY: number) => {
    const startMin = CALENDAR_START_HOUR * 60 + slotIndex * 30;
    const endMin = startMin + 90; // 90-min window covers typical 50–75 min class lengths

    setSlotPopoverData({
      dayIndex,
      slotIndex,
      startMin,
      endMin,
      clientX,
      clientY,
    });
    setSlotPopoverOpen(true);
  }, []);

  return (
    <div className="flex h-screen w-screen flex-col overflow-hidden bg-[var(--scu-white)]">
      <DeleteUserDataConfirm
        open={deleteDataOpen}
        busy={deleteDataBusy}
        error={deleteDataNotice}
        onConfirm={() => void handleConfirmDeleteUserData()}
        onCancel={handleCancelDeleteUserData}
      />
      <FirstLoginCarousel
        open={firstLoginCarouselOpen}
        onFinish={handleFinishFirstLoginCarousel}
      />
      <div className="flex min-h-0 flex-1 overflow-hidden">
      <LeftPanel
        sessions={sessions}
        activeSessionId={activeSessionId}
        onSelectSession={handleSelectSession}
        onDeleteSession={handleDeleteSession}
        onNewPlan={handleNewPlan}
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
          {viewMode === "calendar" && (
            <div className="ml-auto flex items-center pb-1 pr-1">
              <AddCoursePicker existingCodes={effectiveCodes} onAdd={handleAddCourses} />
            </div>
          )}
        </div>

        {viewMode === "calendar" ? (
          <div className="relative min-h-0 flex-1">
            <CalendarView
              recommendedCourses={effectiveRecommended}
              onRemoveCourse={handleRemoveCourse}
              onSlotClick={handleSlotClick}
            />
            {/* Slot suggestion popover (R6) */}
            {slotPopoverOpen && slotPopoverData && (
              <SlotSuggestionPopover
                day_index={slotPopoverData.dayIndex}
                slot_index={slotPopoverData.slotIndex}
                start_min={slotPopoverData.startMin}
                end_min={slotPopoverData.endMin}
                missing_details={missingDetails as Record<string, unknown>[]}
                excluded_courses={effectiveCodes}
                onAddCourse={handleAddFromSlotSuggestion}
                onClose={() => setSlotPopoverOpen(false)}
                client_x={slotPopoverData.clientX}
                client_y={slotPopoverData.clientY}
              />
            )}
          </div>
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
        parsedRows={parsedRows}
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
        focusNonce={chatFocusNonce}
        setParsedRows={setParsedRows}
      />
      </div>
      <SiteFooter
        userId={userId}
        onDeleteUserData={() => setDeleteDataOpen(true)}
        onOpenHelp={() => setFirstLoginCarouselOpen(true)}
      />
    </div>
  );
}

function introSeenKey(userId: string): string {
  return `${INTRO_SEEN_KEY_PREFIX}${userId}`;
}

function hasSeenFirstLoginCarousel(userId: string): boolean {
  try {
    return window.localStorage.getItem(introSeenKey(userId)) === "true";
  } catch {
    return false;
  }
}

function markFirstLoginCarouselSeen(userId: string): void {
  try {
    window.localStorage.setItem(introSeenKey(userId), "true");
  } catch {
    /* If storage is unavailable, still let the user continue in this tab. */
  }
}
