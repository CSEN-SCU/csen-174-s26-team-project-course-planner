import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  deleteAllUserData,
  deleteMemory,
  generateFourYearPlan,
  getMemory,
  saveMemory,
} from "./api/client";
import { CalendarView } from "./components/CalendarView";
import { ChatPanel, type ChatUiMessage } from "./components/ChatPanel";
import {
  CourseBrowser,
  type CourseBrowserAddOptions,
} from "./components/CourseBrowser";
import { FourYearPlanView } from "./components/FourYearPlanView";
import { LeftPanel, type MemorySessionRow } from "./components/LeftPanel";
import type { FourYearPlan, ParsedRow } from "./types";
import { DeleteUserDataConfirm } from "./components/DeleteUserDataConfirm";
import { FirstLoginCarousel } from "./components/FirstLoginCarousel";
import { PlanStartModal } from "./components/PlanStartModal";
import { SlotActionModal } from "./components/SlotActionModal";
import { SlotSuggestionPopover } from "./components/SlotSuggestionPopover";
import type { CatalogSection, CourseBrowserLaunchContext } from "./api/client";
import { CALENDAR_START_HOUR } from "./types";
import { clearLocalSession } from "./auth/session";
import { SiteFooter } from "./components/SiteFooter";

const WELCOME_TEXT =
  "Upload your Academic Progress file or describe your preferences to get started.";
const NEW_PLAN_AI_TEXT =
  "Started a new plan. Upload your Academic Progress file (.xlsx) if you have not yet, then describe your preferences for next quarter.";
const NEW_PLAN_MANUAL_TEXT =
  "Started a new plan. Use Browse courses to search the catalog, or click a time slot on the calendar.";
const INTRO_SEEN_KEY_PREFIX = "scu_planner_intro_seen:";

export type AppProps = {
  userId: string;
  onSignOut: () => void;
};

type PlanSnapshot = {
  id: string;
  memoryId?: number;
  title: string;
  dateLabel: string;
  recommended: Record<string, unknown>[];
  messages?: ChatUiMessage[];
  fourYearPlan?: FourYearPlan | null;
};

function totalUnitsFor(recs: Record<string, unknown>[]): number {
  return recs.reduce((total, row) => {
    const units = Number(row.units);
    return Number.isFinite(units) ? total + units : total;
  }, 0);
}

function withRecommendedCourses(
  plan: Record<string, unknown> | null,
  recs: Record<string, unknown>[],
): Record<string, unknown> {
  return {
    ...(plan ?? {}),
    recommended: recs,
    total_units: totalUnitsFor(recs),
  };
}

function snapshotMemoryPayload(snap: PlanSnapshot): string {
  return JSON.stringify({
    recommended: snap.recommended,
    title: snap.title,
    dateLabel: snap.dateLabel,
    messages: snap.messages,
    fourYearPlan: snap.fourYearPlan ?? null,
  });
}

export default function App({ userId, onSignOut }: AppProps) {
  const [missingDetails, setMissingDetails] = useState<unknown[]>([]);
  const [planResult, setPlanResult] = useState<Record<string, unknown> | null>(null);
  const [messages, setMessages] = useState<ChatUiMessage[]>([
    { id: "m0", role: "assistant", content: WELCOME_TEXT },
  ]);
  const [planSnapshots, setPlanSnapshots] = useState<PlanSnapshot[]>([]);
  const snapshotPersistSeqRef = useRef<Record<string, number>>({});
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
  const [slotActionOpen, setSlotActionOpen] = useState(false);
  const [slotActionData, setSlotActionData] = useState<{
    dayIndex: number;
    slotIndex: number;
    startMin: number;
    endMin: number;
    clientX: number;
    clientY: number;
  } | null>(null);
  const [planStartModalOpen, setPlanStartModalOpen] = useState(false);
  const [courseBrowserOpen, setCourseBrowserOpen] = useState(false);
  const [courseBrowserContext, setCourseBrowserContext] =
    useState<CourseBrowserLaunchContext>({ mode: "open" });

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

  const persistPlanSnapshot = useCallback(
    (snapId: string, snap: PlanSnapshot, previousMemoryId?: number) => {
      if (!userId) return;

      const seq = (snapshotPersistSeqRef.current[snapId] ?? 0) + 1;
      snapshotPersistSeqRef.current[snapId] = seq;

      void saveMemory(userId, "plan_outcome", snapshotMemoryPayload(snap))
        .then((r) => {
          const newId = typeof r?.id === "number" ? r.id : undefined;

          // If a newer save finished or is in-flight, discard this stale row so
          // reload never resurrects an older version of the same conversation.
          if (snapshotPersistSeqRef.current[snapId] !== seq) {
            if (newId != null) {
              void deleteMemory(userId, newId).catch(() => {});
            }
            return;
          }

          if (previousMemoryId != null && previousMemoryId !== newId) {
            void deleteMemory(userId, previousMemoryId).catch(() => {});
          }

          setPlanSnapshots((prev) =>
            prev.map((s) => (s.id === snapId ? { ...s, memoryId: newId } : s)),
          );
        })
        .catch(() => {});
    },
    [userId],
  );

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
      persistPlanSnapshot(existing.id, updated, existing.memoryId);
    } else {
      const snapId = `snap-${Date.now()}`;
      const snap: PlanSnapshot = {
        id: snapId,
        title,
        dateLabel: d,
        recommended: recs,
        messages: msgs,
      };
      setActiveSessionId(snapId);
      setPlanSnapshots((prev) => [snap, ...prev]);
      persistPlanSnapshot(snapId, snap);
    }
  }, [activeSessionId, persistPlanSnapshot, planSnapshots]);

  const resetActivePlanState = useCallback(() => {
    setLocalOverride(null);
    setPlanResult(null);
    setSessionCalendarRecommended(null);
    setFourYearPlan(null);
    setFourYearGenerating(false);
    setActiveSessionId(null);
    setSlotPopoverOpen(false);
    setSlotPopoverData(null);
    setSlotActionOpen(false);
    setSlotActionData(null);
  }, []);

  const openCourseBrowser = useCallback((ctx: CourseBrowserLaunchContext) => {
    setCourseBrowserContext(ctx);
    setCourseBrowserOpen(true);
    setViewMode("calendar");
  }, []);

  const handleNewPlan = useCallback(() => {
    resetActivePlanState();
    setPlanStartModalOpen(true);
  }, [resetActivePlanState]);

  const handlePlanStartManual = useCallback(() => {
    setPlanStartModalOpen(false);
    resetActivePlanState();
    setMessages([{ id: `m-new-${Date.now()}`, role: "assistant", content: NEW_PLAN_MANUAL_TEXT }]);
    openCourseBrowser({ mode: "open" });
  }, [resetActivePlanState, openCourseBrowser, setMessages]);

  const handlePlanStartAi = useCallback(() => {
    setPlanStartModalOpen(false);
    resetActivePlanState();
    setMessages([{ id: `m-new-${Date.now()}`, role: "assistant", content: NEW_PLAN_AI_TEXT }]);
    setViewMode("calendar");
    setChatFocusNonce((n) => n + 1);
  }, [resetActivePlanState, setMessages]);

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

  const commitRecommendedPlan = useCallback(
    (nextRecommended: Record<string, unknown>[]) => {
      const recs = [...nextRecommended];
      const nextPlan = withRecommendedCourses(planResult, recs);
      setLocalOverride(null);
      setPlanResult(nextPlan);
      setSessionCalendarRecommended(recs.length > 0 ? recs : null);

      const existing = activeSessionId
        ? planSnapshots.find((s) => s.id === activeSessionId)
        : null;

      if (recs.length === 0) {
        if (existing) {
          setPlanSnapshots((prev) => prev.filter((s) => s.id !== existing.id));
          if (existing.memoryId != null && userId) {
            void deleteMemory(userId, existing.memoryId).catch(() => {});
          }
        }
        if (activeSessionId === existing?.id) {
          setActiveSessionId(null);
        }
        return;
      }

      const d = new Date().toLocaleDateString();
      const title = `Plan · ${recs.length} courses`;
      if (existing) {
        const updated: PlanSnapshot = {
          ...existing,
          title,
          dateLabel: d,
          recommended: recs,
          messages: existing.messages ?? messages,
          fourYearPlan: existing.fourYearPlan ?? fourYearPlan,
        };
        setPlanSnapshots((prev) =>
          prev.map((s) => (s.id === existing.id ? updated : s)),
        );
        persistPlanSnapshot(existing.id, updated, existing.memoryId);
        return;
      }

      const snapId = `snap-${Date.now()}`;
      const snap: PlanSnapshot = {
        id: snapId,
        title,
        dateLabel: d,
        recommended: recs,
        messages,
        fourYearPlan,
      };
      setActiveSessionId(snapId);
      setPlanSnapshots((prev) => [snap, ...prev]);
      persistPlanSnapshot(snapId, snap);
    },
    [
      activeSessionId,
      fourYearPlan,
      messages,
      persistPlanSnapshot,
      planResult,
      planSnapshots,
      userId,
    ],
  );

  const handleRemoveCourse = useCallback((idx: number) => {
    const base = effectiveRecommended ?? [];
    commitRecommendedPlan(base.filter((_, i) => i !== idx));
  }, [commitRecommendedPlan, effectiveRecommended]);

  // Manual "+ Add course": append picked courses (+ lab co-requisite) to the
  // live edit layer so they land on the calendar immediately — no AI call.
  function formatMeetingLabel(startMin: number | null, endMin: number | null): string | undefined {
    if (startMin == null || endMin == null || startMin >= endMin) return undefined;
    const base = CALENDAR_START_HOUR * 60;
    const fmt = (off: number) => {
      const total = base + off;
      const h = Math.floor(total / 60);
      const m = total % 60;
      const d = new Date();
      d.setHours(h, m, 0, 0);
      return d.toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit", hour12: true });
    };
    return `${fmt(startMin)} – ${fmt(endMin)}`;
  }

  const appendPlanCourses = useCallback(
    (additions: Record<string, unknown>[]) => {
      if (additions.length === 0) return;
      const base = effectiveRecommended ?? [];
      commitRecommendedPlan([...base, ...additions]);
    },
    [commitRecommendedPlan, effectiveRecommended],
  );

  const handleAddFromCatalog = useCallback(
    (sections: CatalogSection[], options?: CourseBrowserAddOptions) => {
      const base = effectiveRecommended ?? [];
      const present = new Set(
        base.map((r) => String((r as { course?: unknown }).course ?? "").trim().toUpperCase()),
      );
      const anchor = options?.slotAnchor;
      const additions = sections
        .filter((s) => !present.has(s.course.trim().toUpperCase()))
        .map((s) => {
          const row: Record<string, unknown> = {
            course: s.course,
            title: s.title ?? undefined,
            units: s.units ?? undefined,
            best_professor: s.instructors?.[0] ?? undefined,
            meeting_days: s.meeting_days,
            meeting_start_min: s.meeting_start_min,
            meeting_end_min: s.meeting_end_min,
            category: "Manually added",
            reason: "Added manually",
            _manualAdd: true,
            _section: s.section,
          };
          if (anchor) {
            row._slotAnchored = true;
            row._anchoredDayIndex = anchor.dayIndex;
            row._anchoredStartMin = anchor.startMin;
            row._anchoredEndMin = anchor.endMin;
            row._actualTimeLabel = formatMeetingLabel(s.meeting_start_min, s.meeting_end_min);
          }
          return row;
        });
      appendPlanCourses(additions);
    },
    [effectiveRecommended, appendPlanCourses],
  );

  // Add course from slot suggestion popover (R6)
  const handleAddFromSlotSuggestion = useCallback((course: Record<string, unknown>) => {
    const base = effectiveRecommended ?? [];
    const courseCode = String(course.course ?? "").trim().toUpperCase();
    const present = new Set(
      base.map((r) => String((r as { course?: unknown }).course ?? "").trim().toUpperCase()),
    );
    if (present.has(courseCode)) return;
    commitRecommendedPlan([...base, { ...course, _slotSuggestion: true }]);
  }, [commitRecommendedPlan, effectiveRecommended]);

  const effectiveCodes = useMemo(
    () =>
      (effectiveRecommended ?? []).map((r) =>
        String((r as { course?: unknown }).course ?? ""),
      ),
    [effectiveRecommended],
  );

  // Slot-add UX: prevent users from repeatedly filling the same requirement (e.g. SJ/Medical SJ)
  // by filtering already-satisfied requirement labels out of `missing_details` before requesting
  // slot suggestions. This keeps the popover honest and avoids "double counting".
  const satisfiedCoverLabels = useMemo(() => {
    const out: string[] = [];
    for (const r of effectiveRecommended ?? []) {
      const covers = (r as { covers?: unknown }).covers;
      if (!Array.isArray(covers)) continue;
      for (const c of covers) {
        const s = typeof c === "string" ? c.trim() : "";
        if (s && !out.includes(s)) out.push(s);
      }
    }
    return out;
  }, [effectiveRecommended]);

  function _normCover(s: string): string {
    return (s || "")
      .toLowerCase()
      .replace(/\s+/g, " ")
      .replace(/[()（）、,.:;·/\\\-]+/g, " ")
      .trim();
  }

  const missingDetailsForSlot = useMemo(() => {
    if (!Array.isArray(missingDetails) || missingDetails.length === 0) return [];
    if (!Array.isArray(satisfiedCoverLabels) || satisfiedCoverLabels.length === 0) return missingDetails;

    const satisfied = satisfiedCoverLabels.map(_normCover).filter(Boolean);
    if (satisfied.length === 0) return missingDetails;

    return missingDetails.filter((row) => {
      if (!row || typeof row !== "object") return true;
      const r = row as Record<string, unknown>;
      const raw =
        (typeof r.requirement === "string" && r.requirement) ||
        (typeof r.Requirement === "string" && r.Requirement) ||
        (typeof r.category === "string" && r.category) ||
        (typeof r.Category === "string" && r.Category) ||
        "";
      const hay = _normCover(raw);
      if (!hay) return true;
      // If any satisfied cover label is mentioned by this missing-detail row,
      // treat it as already satisfied by a previously slot-added course.
      return !satisfied.some((lab) => hay.includes(lab));
    });
  }, [missingDetails, satisfiedCoverLabels]);

  /** Last user chat line — passed to slot popover for enrichment direction (e.g. 中文). */
  const slotUserPreference = useMemo(() => {
    for (let i = messages.length - 1; i >= 0; i--) {
      if (messages[i].role === "user") {
        return messages[i].content.trim();
      }
    }
    return "";
  }, [messages]);

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
        persistPlanSnapshot(targetSnap.id, updated, targetSnap.memoryId);
      }
    } catch (e) {
      console.error("Four-year plan generation failed:", e);
    } finally {
      setFourYearGenerating(false);
    }
  }, [missingDetails, userId, fourYearGenerating, activeSessionId, planSnapshots, persistPlanSnapshot]);

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

  const slotTimeLabel = useCallback((dayIndex: number, startMin: number, endMin: number) => {
    const base = CALENDAR_START_HOUR * 60;
    const fmt = (off: number) => {
      const total = base + off;
      const h = Math.floor(total / 60);
      const m = total % 60;
      const d = new Date();
      d.setHours(h, m, 0, 0);
      return d.toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit", hour12: true });
    };
    const dayNames = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"];
    return `${dayNames[dayIndex] ?? "Day"} ${fmt(startMin)} – ${fmt(endMin)}`;
  }, []);

  const handleSlotClick = useCallback((dayIndex: number, slotIndex: number, clientX: number, clientY: number) => {
    const startMin = slotIndex * 30;
    const endMin = startMin + 30;
    setSlotActionData({ dayIndex, slotIndex, startMin, endMin, clientX, clientY });
    setSlotActionOpen(true);
    setSlotPopoverOpen(false);
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
      <PlanStartModal
        open={planStartModalOpen}
        onManual={handlePlanStartManual}
        onAi={handlePlanStartAi}
        onClose={() => setPlanStartModalOpen(false)}
      />
      <CourseBrowser
        open={courseBrowserOpen}
        context={courseBrowserContext}
        existingCodes={effectiveCodes}
        onAdd={handleAddFromCatalog}
        onClose={() => setCourseBrowserOpen(false)}
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
              <button
                type="button"
                onClick={() => openCourseBrowser({ mode: "open" })}
                className="flex items-center gap-1 rounded-md border border-[var(--scu-red)] px-2.5 py-1 text-xs font-semibold text-[var(--scu-red)] transition hover:bg-red-50"
              >
                Browse courses
              </button>
            </div>
          )}
        </div>

        {viewMode === "calendar" ? (
          <div className="relative min-h-0 flex-1">
            <CalendarView
              recommendedCourses={effectiveRecommended ?? []}
              onRemoveCourse={handleRemoveCourse}
              onSlotClick={handleSlotClick}
            />
            {slotActionOpen && slotActionData && (
              <SlotActionModal
                open={slotActionOpen}
                dayIndex={slotActionData.dayIndex}
                startMin={slotActionData.startMin}
                endMin={slotActionData.endMin}
                clientX={slotActionData.clientX}
                clientY={slotActionData.clientY}
                onClose={() => setSlotActionOpen(false)}
                onBrowse={() => {
                  const d = slotActionData;
                  setSlotActionOpen(false);
                  openCourseBrowser({
                    mode: "slot",
                    dayIndex: d.dayIndex,
                    startMin: d.startMin,
                    endMin: d.endMin,
                    label: slotTimeLabel(d.dayIndex, d.startMin, d.endMin),
                  });
                }}
                onAiSuggest={() => {
                  setSlotActionData(slotActionData);
                  setSlotPopoverData(slotActionData);
                  setSlotActionOpen(false);
                  setSlotPopoverOpen(true);
                }}
              />
            )}
            {/* Slot suggestion popover (R6) */}
            {slotPopoverOpen && slotPopoverData && (
              <SlotSuggestionPopover
                day_index={slotPopoverData.dayIndex}
                slot_index={slotPopoverData.slotIndex}
                start_min={slotPopoverData.startMin}
                end_min={slotPopoverData.endMin}
                missing_details={missingDetailsForSlot as Record<string, unknown>[]}
                excluded_courses={effectiveCodes}
                satisfied_covers={satisfiedCoverLabels}
                user_preference={slotUserPreference}
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
