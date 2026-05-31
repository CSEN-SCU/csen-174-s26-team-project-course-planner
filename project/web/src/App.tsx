import { useCallback, useEffect, useMemo, useState } from "react";
import {
  deleteMemory,
  detectStudentMajor,
  generateFourYearPlan,
  getMemory,
  saveMemory,
  type MajorDetection,
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
import { FirstLoginCarousel } from "./components/FirstLoginCarousel";
import { PlanStartModal } from "./components/PlanStartModal";
import { SlotActionModal } from "./components/SlotActionModal";
import { SlotSuggestionPopover } from "./components/SlotSuggestionPopover";
import type { CatalogSection, CourseBrowserLaunchContext } from "./api/client";
import { CALENDAR_START_HOUR } from "./types";
import { SiteFooter } from "./components/SiteFooter";
import { CourseSwapModal } from "./components/CourseSwapModal";
import { SaveScheduleModal } from "./components/SaveScheduleModal";
import { NewPlanWarningModal } from "./components/NewPlanWarningModal";
import { DeleteScheduleConfirmModal } from "./components/DeleteScheduleConfirmModal";
import { PlannerColumnHeader } from "./components/PlannerColumnHeader";

const WELCOME_TEXT =
  "Upload your Academic Progress file or describe your preferences to get started.";
const NEW_PLAN_AI_TEXT =
  "Started a new plan. Upload your Academic Progress file (.xlsx) if you have not yet, then describe your preferences for next quarter.";
const PROGRESS_LOADED_TEXT =
  "Your Academic Progress is already loaded. Tell me what kind of schedule you want for next quarter.";
const NEW_PLAN_AI_WITH_PROGRESS_TEXT =
  "Started a new plan. Your Academic Progress is already loaded, so tell me your preferences for next quarter.";
const NEW_PLAN_MANUAL_TEXT =
  "Started a new plan. Use Browse courses to search the catalog, or click a time slot on the calendar.";
const INTRO_SEEN_KEY_PREFIX = "scu_planner_intro_seen:";

export type AppProps = {
  userId: string;
  onSignOut: () => void;
  onDeleteUserData: () => void;
};

export default function App({ userId, onSignOut, onDeleteUserData }: AppProps) {
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
  const [studentMajorId, setStudentMajorId] = useState<string | null>(null);
  const [majorConfirmed, setMajorConfirmed] = useState(false);
  const [majorDetection, setMajorDetection] = useState<MajorDetection | null>(null);
  const [majorEditMode, setMajorEditMode] = useState(false);
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
  const [swapModalOpen, setSwapModalOpen] = useState(false);
  const [swapModalData, setSwapModalData] = useState<{
    index: number;
    courseCode: string;
    section?: number;
  } | null>(null);
  const [saveScheduleModalOpen, setSaveScheduleModalOpen] = useState(false);
  const [newPlanWarningOpen, setNewPlanWarningOpen] = useState(false);
  const [startNewPlanAfterSave, setStartNewPlanAfterSave] = useState(false);
  const [pendingDeleteSchedule, setPendingDeleteSchedule] = useState<{
    id: string;
    title: string;
  } | null>(null);

  // Load academic progress + past plan snapshots for this user
  useEffect(() => {
    void getMemory(userId)
      .then((r) => {
        const mems: Record<string, unknown>[] = Array.isArray(r.memories) ? r.memories : [];
        let restoredAcademicProgress = false;

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
              restoredAcademicProgress = true;
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
              setFileUploaded(true);
              restoredAcademicProgress = true;
            }
          } catch { /* ignore */ }
        }

        const majorItems = mems
          .filter((m) => m.kind === "student_major")
          .sort((a, b) => String(b.created_at ?? "").localeCompare(String(a.created_at ?? "")));
        if (majorItems.length > 0) {
          try {
            const sm = JSON.parse(String(majorItems[0].content ?? "{}")) as {
              major_id?: string;
              name?: string;
              confirmed?: boolean;
            };
            if (sm.major_id) {
              setStudentMajorId(sm.major_id);
              setMajorConfirmed(Boolean(sm.confirmed));
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

        if (restoredAcademicProgress) {
          setMessages((prev) =>
            prev.length === 1 && prev[0]?.content === WELCOME_TEXT
              ? [{ ...prev[0], content: PROGRESS_LOADED_TEXT }]
              : prev,
          );
        }
      })
      .catch(() => { /* ignore */ });
  }, [userId]);

  const clearTranscriptMemory = useCallback(async () => {
    try {
      const r = await getMemory(userId);
      const mems: Record<string, unknown>[] = Array.isArray(r.memories) ? r.memories : [];
      await Promise.all(
        mems
          .filter((m) =>
            m.kind === "academic_progress" ||
            m.kind === "parsed_rows" ||
            m.kind === "student_major",
          )
          .map((m) =>
            typeof m.id === "number" ? deleteMemory(userId, m.id).catch(() => {}) : Promise.resolve(),
          ),
      );
    } catch {
      /* ignore */
    }
  }, [userId]);

  const refreshMajorDetection = useCallback(async () => {
    if (!fileUploaded || missingDetails.length === 0) return;
    try {
      const det = await detectStudentMajor(
        missingDetails,
        parsedRows,
        majorConfirmed ? studentMajorId ?? undefined : undefined,
      );
      if (!majorConfirmed) {
        setMajorDetection(det);
        if (det.major_id && !studentMajorId) {
          setStudentMajorId(det.major_id);
        }
      }
    } catch {
      /* ignore */
    }
  }, [fileUploaded, missingDetails, parsedRows, majorConfirmed, studentMajorId]);

  useEffect(() => {
    if (fileUploaded && !majorConfirmed) {
      void refreshMajorDetection();
    }
  }, [fileUploaded, missingDetails, parsedRows, majorConfirmed, refreshMajorDetection]);

  useEffect(() => {
    setFirstLoginCarouselOpen(!hasSeenFirstLoginCarousel(userId));
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

  const scheduleCourseCount = (effectiveRecommended ?? []).length;

  const hasUnsavedScheduleEdits =
    scheduleCourseCount > 0 &&
    (localOverride !== null || (activeSessionId?.startsWith("draft-") ?? false));

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

  const beginNewPlanFlow = useCallback(() => {
    resetActivePlanState();
    setPlanStartModalOpen(true);
  }, [resetActivePlanState]);

  const startDraftPlanSession = useCallback(() => {
    setActiveSessionId(`draft-${Date.now()}`);
  }, []);

  const persistScheduleSnapshot = useCallback(
    (scheduleName: string) => {
      const recs = localOverride ?? calendarRecommended ?? [];
      if (recs.length === 0) return false;

      const title = scheduleName.trim();
      if (!title) return false;

      const d = new Date().toLocaleDateString();
      const msgs = messages;
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
        } else if (userId) {
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
        const priorId = activeSessionId;
        const snapId = priorId?.startsWith("draft-")
          ? `snap-${Date.now()}`
          : priorId ?? `snap-${Date.now()}`;
        setActiveSessionId(snapId);
        const snap = {
          id: snapId,
          title,
          dateLabel: d,
          recommended: recs,
          messages: msgs,
          fourYearPlan: fourYearPlan ?? null,
        };
        setPlanSnapshots((prev) => [
          snap,
          ...prev.filter((s) => s.id !== snapId && s.id !== priorId),
        ]);
        if (userId) {
          void saveMemory(
            userId,
            "plan_outcome",
            JSON.stringify({
              recommended: recs,
              title,
              dateLabel: d,
              messages: msgs,
              fourYearPlan: fourYearPlan ?? null,
            }),
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

      setLocalOverride(null);
      setSessionCalendarRecommended(recs);
      setPlanResult({ recommended: recs });
      return true;
    },
    [
      localOverride,
      calendarRecommended,
      messages,
      activeSessionId,
      planSnapshots,
      userId,
      fourYearPlan,
    ],
  );

  const openCourseBrowser = useCallback((ctx: CourseBrowserLaunchContext) => {
    setCourseBrowserContext(ctx);
    setCourseBrowserOpen(true);
    setViewMode("calendar");
  }, []);

  const handleNewPlan = useCallback(() => {
    if (hasUnsavedScheduleEdits) {
      setNewPlanWarningOpen(true);
      return;
    }
    beginNewPlanFlow();
  }, [hasUnsavedScheduleEdits, beginNewPlanFlow]);

  const handleClearSchedule = useCallback(() => {
    setLocalOverride([]);
    setPlanResult({ recommended: [] });
    setSessionCalendarRecommended([]);
  }, []);

  const handleSaveScheduleNamed = useCallback(
    (name: string) => {
      if (!persistScheduleSnapshot(name)) return;
      setSaveScheduleModalOpen(false);
      if (startNewPlanAfterSave) {
        setStartNewPlanAfterSave(false);
        beginNewPlanFlow();
      }
    },
    [persistScheduleSnapshot, startNewPlanAfterSave, beginNewPlanFlow],
  );

  const handlePlanStartManual = useCallback(() => {
    setPlanStartModalOpen(false);
    resetActivePlanState();
    startDraftPlanSession();
    setMessages([{ id: `m-new-${Date.now()}`, role: "assistant", content: NEW_PLAN_MANUAL_TEXT }]);
    openCourseBrowser({ mode: "open" });
  }, [resetActivePlanState, startDraftPlanSession, openCourseBrowser, setMessages]);

  const handlePlanStartAi = useCallback(() => {
    setPlanStartModalOpen(false);
    resetActivePlanState();
    startDraftPlanSession();
    setMessages([{
      id: `m-new-${Date.now()}`,
      role: "assistant",
      content: fileUploaded ? NEW_PLAN_AI_WITH_PROGRESS_TEXT : NEW_PLAN_AI_TEXT,
    }]);
    setViewMode("calendar");
    setChatFocusNonce((n) => n + 1);
  }, [fileUploaded, resetActivePlanState, startDraftPlanSession, setMessages]);

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

  const requestDeleteSession = useCallback(
    (id: string) => {
      const snap = planSnapshots.find((s) => s.id === id);
      if (!snap) return;
      setPendingDeleteSchedule({ id, title: snap.title });
    },
    [planSnapshots],
  );

  const handleConfirmDeleteSession = useCallback(() => {
    if (!pendingDeleteSchedule) return;
    handleDeleteSession(pendingDeleteSchedule.id);
    setPendingDeleteSchedule(null);
  }, [pendingDeleteSchedule, handleDeleteSession]);

  const handleRemoveCourse = useCallback((idx: number) => {
    const base = localOverride ?? calendarRecommended ?? [];
    setLocalOverride(base.filter((_, i) => i !== idx));
  }, [localOverride, calendarRecommended]);

  const handleCourseClick = useCallback(
    (idx: number, courseCode: string) => {
      const base = localOverride ?? calendarRecommended ?? [];
      const row = base[idx] as { _section?: unknown } | undefined;
      const section =
        typeof row?._section === "number"
          ? row._section
          : typeof row?._section === "string"
            ? Number(row._section)
            : undefined;
      setSwapModalData({ index: idx, courseCode, section });
      setSwapModalOpen(true);
    },
    [localOverride, calendarRecommended],
  );

  const handleSwapCourseSection = useCallback(
    (section: CatalogSection) => {
      if (!swapModalData) return;
      const base = [...(localOverride ?? calendarRecommended ?? [])];
      const i = swapModalData.index;
      if (!base[i]) return;
      const curr = base[i] as Record<string, unknown>;
      base[i] = {
        ...curr,
        course: section.course,
        title: section.title ?? curr.title,
        units: section.units ?? curr.units,
        best_professor: section.instructors?.[0] ?? curr.best_professor,
        meeting_days: section.meeting_days,
        meeting_start_min: section.meeting_start_min,
        meeting_end_min: section.meeting_end_min,
        _section: section.section,
        _slotAnchored: false,
        _anchoredDayIndex: undefined,
        _anchoredStartMin: undefined,
        _anchoredEndMin: undefined,
        _actualTimeLabel: undefined,
      };
      setLocalOverride(base);
      setSwapModalOpen(false);
      setSwapModalData(null);
    },
    [swapModalData, localOverride, calendarRecommended],
  );

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
      const base = localOverride ?? calendarRecommended ?? [];
      setLocalOverride([...base, ...additions]);
    },
    [localOverride, calendarRecommended],
  );

  const handleAddFromCatalog = useCallback(
    (sections: CatalogSection[], options?: CourseBrowserAddOptions) => {
      const base = localOverride ?? calendarRecommended ?? [];
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
    [localOverride, calendarRecommended, appendPlanCourses],
  );

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

  const majorReadyForPlanning = majorConfirmed && !majorEditMode && !!studentMajorId;

  const handleGenerateFourYearPlan = useCallback(async (preferences: string) => {
    if (!missingDetails.length || fourYearGenerating) return;
    setFourYearGenerating(true);
    try {
      if (!majorReadyForPlanning) {
        setMessages((m) => [
          ...m,
          {
            id: `a-${Date.now()}`,
            role: "assistant",
            content: "Please confirm your major in the chat panel before generating a four-year plan.",
          },
        ]);
        setFourYearGenerating(false);
        return;
      }

      const result = await generateFourYearPlan(
        missingDetails,
        userId ?? "anonymous",
        preferences.trim() || undefined,
        parsedRows,
        studentMajorId,
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
  }, [
    missingDetails,
    userId,
    fourYearGenerating,
    activeSessionId,
    planSnapshots,
    majorReadyForPlanning,
    studentMajorId,
    parsedRows,
  ]);

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
    <div className="flex min-h-0 w-full flex-1 flex-col overflow-hidden">
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
      <SaveScheduleModal
        open={saveScheduleModalOpen}
        defaultName={
          scheduleCourseCount > 0
            ? `Plan · ${scheduleCourseCount} courses`
            : ""
        }
        courseCount={scheduleCourseCount}
        onSave={handleSaveScheduleNamed}
        onClose={() => {
          setSaveScheduleModalOpen(false);
          setStartNewPlanAfterSave(false);
        }}
      />
      <NewPlanWarningModal
        open={newPlanWarningOpen}
        onSaveFirst={() => {
          setNewPlanWarningOpen(false);
          setStartNewPlanAfterSave(true);
          setSaveScheduleModalOpen(true);
        }}
        onStartWithoutSaving={() => {
          setNewPlanWarningOpen(false);
          beginNewPlanFlow();
        }}
        onCancel={() => setNewPlanWarningOpen(false)}
      />
      <DeleteScheduleConfirmModal
        open={pendingDeleteSchedule !== null}
        scheduleTitle={pendingDeleteSchedule?.title ?? ""}
        onConfirm={handleConfirmDeleteSession}
        onCancel={() => setPendingDeleteSchedule(null)}
      />
      <CourseBrowser
        open={courseBrowserOpen}
        context={courseBrowserContext}
        existingCodes={effectiveCodes}
        onAdd={handleAddFromCatalog}
        onClose={() => setCourseBrowserOpen(false)}
      />
      <CourseSwapModal
        open={swapModalOpen && swapModalData !== null}
        courseCode={swapModalData?.courseCode ?? ""}
        currentSection={swapModalData?.section}
        onClose={() => {
          setSwapModalOpen(false);
          setSwapModalData(null);
        }}
        onRemove={() => {
          if (swapModalData) handleRemoveCourse(swapModalData.index);
          setSwapModalOpen(false);
          setSwapModalData(null);
        }}
        onSwap={handleSwapCourseSection}
      />
      <div className="planner-workspace">
      <LeftPanel
        sessions={sessions}
        activeSessionId={activeSessionId}
        scheduleCourseCount={scheduleCourseCount}
        onSelectSession={handleSelectSession}
        onDeleteSession={requestDeleteSession}
        onNewPlan={handleNewPlan}
        onSaveSchedule={() => setSaveScheduleModalOpen(true)}
        onClearSchedule={handleClearSchedule}
      />

      {/* Main view area with tab toggle */}
      <div className="flex h-full min-h-0 min-w-0 flex-col overflow-hidden">
        <PlannerColumnHeader variant="toolbar" align="between">
          <div className="flex w-full min-w-0 items-end">
            <button
              type="button"
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
              type="button"
              className={`px-4 py-2 text-xs font-semibold border-b-2 transition ${
                viewMode === "four-year"
                  ? "border-[var(--scu-red)] text-[var(--scu-red)]"
                  : "border-transparent text-neutral-400 hover:text-neutral-600"
              }`}
              onClick={() => setViewMode("four-year")}
            >
              Four-Year Plan
            </button>
            {viewMode === "calendar" ? (
              <div className="ml-auto flex items-center pb-1 pr-1">
                <button
                  type="button"
                  onClick={() => openCourseBrowser({ mode: "open" })}
                  className="flex items-center gap-1 rounded-md border border-[var(--scu-red)] px-2.5 py-1 text-xs font-semibold text-[var(--scu-red)] transition hover:bg-red-50"
                >
                  Browse courses
                </button>
              </div>
            ) : (
              <div className="ml-auto flex items-center pb-1 pr-1">
                <button
                  type="button"
                  onClick={() => handleGenerateFourYearPlan("")}
                  disabled={fourYearGenerating || !fileUploaded || !majorReadyForPlanning}
                  className="flex items-center gap-1.5 rounded-md bg-[var(--scu-red)] px-3 py-1.5 text-xs font-semibold text-white shadow-sm transition hover:bg-red-700 disabled:cursor-not-allowed disabled:opacity-50"
                >
                  {fourYearGenerating
                    ? "Generating…"
                    : fourYearPlan
                      ? "Regenerate"
                      : "Generate Plan"}
                </button>
              </div>
            )}
          </div>
        </PlannerColumnHeader>

        {viewMode === "calendar" ? (
          <div className="relative flex min-h-0 flex-1 flex-col">
            <CalendarView
              recommendedCourses={effectiveRecommended ?? []}
              onRemoveCourse={handleRemoveCourse}
              onSlotClick={handleSlotClick}
              onCourseClick={handleCourseClick}
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
        studentMajorId={studentMajorId}
        majorConfirmed={majorConfirmed && !majorEditMode}
        majorDetection={majorDetection}
        onSelectMajor={(id) => {
          setStudentMajorId(id);
        }}
        onMajorConfirmed={() => {
          setMajorConfirmed(true);
          setMajorEditMode(false);
        }}
        onRequestMajorChange={() => {
          setMajorEditMode(true);
          setMajorConfirmed(false);
        }}
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
        onSignOut={onSignOut}
        onTranscriptUploaded={(det) => {
          setMajorDetection(det ?? null);
          setMajorConfirmed(false);
          setMajorEditMode(false);
          if (det?.major_id) {
            setStudentMajorId(det.major_id);
          } else {
            setStudentMajorId(null);
          }
        }}
        onDiscardTranscript={clearTranscriptMemory}
      />
      </div>
      <SiteFooter
        userId={userId}
        onDeleteUserData={onDeleteUserData}
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
