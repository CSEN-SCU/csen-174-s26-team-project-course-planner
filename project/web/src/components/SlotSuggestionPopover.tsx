import { useEffect, useRef, useState } from "react";
import {
  suggestCoursesForSlot,
  type CourseSuggestion,
  type EnrichmentSlotSuggestions,
} from "../api/client";
import { CALENDAR_START_HOUR } from "../types";

export type SlotSuggestionPopoverProps = {
  day_index: number;
  slot_index: number;
  start_min: number;
  end_min: number;
  missing_details: Record<string, unknown>[];
  excluded_courses: string[];
  /** Requirement labels already satisfied by slot-added courses (e.g. Social Justice). */
  satisfied_covers?: string[];
  /** Recent chat text — infers enrichment direction (e.g. 中文 → CHIN). */
  user_preference?: string;
  onAddCourse: (course: Record<string, unknown>) => void;
  onClose: () => void;
  /** Viewport coordinates of the click that opened the popover */
  client_x: number;
  client_y: number;
};

const POPOVER_WIDTH = 320;
const POPOVER_MAX_HEIGHT = 420;

/** Clamp the popover inside the viewport with a 12 px margin. */
function clampPosition(cx: number, cy: number): { top: number; left: number } {
  const vw = window.innerWidth;
  const vh = window.innerHeight;
  const left = Math.min(cx + 8, vw - POPOVER_WIDTH - 12);
  const top = cy + POPOVER_MAX_HEIGHT + 8 > vh ? cy - POPOVER_MAX_HEIGHT - 8 : cy + 8;
  return { top: Math.max(12, top), left: Math.max(12, left) };
}

export function SlotSuggestionPopover({
  day_index,
  start_min,
  end_min,
  missing_details,
  excluded_courses,
  satisfied_covers = [],
  user_preference = "",
  onAddCourse,
  onClose,
  client_x,
  client_y,
}: SlotSuggestionPopoverProps) {
  const [candidates, setCandidates] = useState<CourseSuggestion[]>([]);
  const [enrichment, setEnrichment] = useState<EnrichmentSlotSuggestions | null>(null);
  const [emptyMessage, setEmptyMessage] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // Codes shown so-far (excluded on Show-more requests)
  const [shownCodes, setShownCodes] = useState<string[]>(excluded_courses);

  const popoverRef = useRef<HTMLDivElement>(null);
  const { top, left } = clampPosition(client_x, client_y);

  // Click-outside to close
  useEffect(() => {
    function handleDocClick(e: MouseEvent) {
      if (popoverRef.current && !popoverRef.current.contains(e.target as Node)) {
        onClose();
      }
    }
    document.addEventListener("mousedown", handleDocClick);
    return () => document.removeEventListener("mousedown", handleDocClick);
  }, [onClose]);

  // Initial fetch
  useEffect(() => {
    setLoading(true);
    setError(null);
    setEmptyMessage(null);
    suggestCoursesForSlot({
      day_index,
      start_min,
      end_min,
      missing_details,
      exclude_codes: excluded_courses,
      user_preference,
    })
      .then((res) => {
        setCandidates(res.candidates);
        setEnrichment(res.enrichment);
        setEmptyMessage(res.message ?? null);
        const codes = [
          ...res.candidates.map((c) => c.course),
          ...(res.enrichment?.candidates ?? []).map((c) => c.course),
        ];
        setShownCodes([...excluded_courses, ...codes]);
      })
      .catch((err) => {
        setError(err instanceof Error ? err.message : "Failed to load suggestions");
      })
      .finally(() => {
        setLoading(false);
      });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [day_index, start_min, end_min, user_preference]);

  const handleAddCourse = (candidate: CourseSuggestion) => {
    onAddCourse({
      course: candidate.course,
      title: candidate.title,
      units: candidate.units,
      category: candidate.kind === "enrichment" ? "Educational Enrichment" : "",
      reason: candidate.rationale,
      best_professor: candidate.instructor,
      meeting_days: candidate.meeting_days,
      meeting_start_min: candidate.meeting_start_min,
      meeting_end_min: candidate.meeting_end_min,
      covers: candidate.covers,
    });
    onClose();
  };

  const handleShowMore = () => {
    setLoadingMore(true);
    suggestCoursesForSlot({
      day_index,
      start_min,
      end_min,
      missing_details,
      exclude_codes: shownCodes,
      user_preference,
    })
      .then((res) => {
        const newCore = res.candidates;
        const enrich = res.enrichment;
        const newEnrich = enrich?.candidates ?? [];
        if (newCore.length === 0 && newEnrich.length === 0) return;
        if (newCore.length > 0) {
          setCandidates((prev) => [...prev, ...newCore]);
        }
        if (enrich) {
          setEnrichment((prev) => (prev ? { ...prev, candidates: [...prev.candidates, ...newEnrich] } : enrich));
        }
        setShownCodes((prev) => [
          ...prev,
          ...newCore.map((c) => c.course),
          ...newEnrich.map((c) => c.course),
        ]);
      })
      .catch(() => {/* silent — best effort */})
      .finally(() => setLoadingMore(false));
  };

  const dayNames = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
  // `start_min` is minutes-from-calendar-start (8:00 AM) so we add the offset
  // to render a human-readable clock time.
  const startTotal = CALENDAR_START_HOUR * 60 + start_min;
  const hour = Math.floor(startTotal / 60);
  const min = startTotal % 60;
  const timeStr = `${hour % 12 || 12}:${String(min).padStart(2, "0")} ${hour < 12 ? "AM" : "PM"}`;

  const enrichList = enrichment?.candidates ?? [];
  const hasAny = candidates.length > 0 || enrichList.length > 0;

  return (
    <div
      ref={popoverRef}
      className="fixed z-50 bg-white rounded-xl shadow-xl border border-neutral-200 overflow-hidden"
      style={{
        top,
        left,
        width: POPOVER_WIDTH,
        maxHeight: POPOVER_MAX_HEIGHT,
        overflowY: "auto",
      }}
      onClick={(e) => e.stopPropagation()}
    >
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-neutral-100 bg-neutral-50 sticky top-0 z-10">
        <h3 className="text-xs font-bold text-neutral-700 uppercase tracking-wide">
          {dayNames[day_index]} · {timeStr}
        </h3>
        <button
          onClick={onClose}
          className="rounded p-1 text-neutral-400 hover:text-neutral-600 hover:bg-neutral-100 transition"
          aria-label="Close"
        >
          <XIcon />
        </button>
      </div>

      <div className="p-3 space-y-2">
        {/* Loading skeleton */}
        {loading && (
          <div className="space-y-2 py-1">
            {[1, 2, 3].map((i) => (
              <div key={i} className="h-14 rounded-lg bg-neutral-100 animate-pulse" />
            ))}
          </div>
        )}

        {/* Error */}
        {!loading && error && (
          <div className="text-xs text-red-600 bg-red-50 rounded-lg px-3 py-2">
            {error}
          </div>
        )}

        {/* Empty (no core and no enrichment at this slot) */}
        {!loading && !error && !hasAny && (
          <p className="text-xs text-neutral-600 leading-relaxed text-center py-4 px-1">
            {emptyMessage ??
              "No courses at this time slot fill your remaining requirements. Try another slot, or tell the chat which requirement to prioritize."}
          </p>
        )}

        {/* Enrichment block — department sequence (e.g. 中文 / CHIN) */}
        {!loading && !error && enrichment && (
          <div className="rounded-lg border border-amber-200 bg-amber-50/80 px-3 py-2 space-y-2">
            <div>
              <p className="text-[11px] font-bold uppercase tracking-wide text-amber-900">
                Enrichment picks
              </p>
              <p className="text-xs font-semibold text-amber-950 mt-0.5">
                Track: {enrichment.track_label || "Not specified"}
              </p>
              <p className="text-[11px] text-amber-900/80 mt-1 leading-relaxed">
                Courses starting with <span className="font-mono">CHIN</span>, or titles containing
                Chinese.
              </p>
              {enrichment.prompt && (
                <p className="text-[11px] text-amber-800 mt-1 leading-relaxed">{enrichment.prompt}</p>
              )}
            </div>
            {enrichList.length === 0 ? (
              <p className="text-[11px] text-amber-800 text-center py-2">
                No enrichment courses in this track fit this time slot. Try another time or change
                your track in chat.
              </p>
            ) : (
              enrichList.map((c) => (
                <CandidateCard
                  key={`enrich-${c.course}`}
                  c={c}
                  onAdd={() => handleAddCourse(c)}
                  addDisabled={isAlreadySatisfied(c, satisfied_covers)}
                  badgeClass="bg-amber-100 text-amber-900 border-amber-200"
                />
              ))
            )}
          </div>
        )}

        {/* Core / other requirement fills */}
        {!loading && !error && candidates.length > 0 && (
          <p className="text-[10px] font-bold uppercase tracking-wide text-neutral-500 px-0.5">
            Other open requirements
          </p>
        )}
        {!loading && !error &&
          candidates.map((c) => (
            <CandidateCard
              key={c.course}
              c={c}
              onAdd={() => handleAddCourse(c)}
              addDisabled={isAlreadySatisfied(c, satisfied_covers)}
              badgeClass="bg-red-50 text-[var(--scu-red)] border-red-100"
            />
          ))}

        {/* Show more */}
        {!loading && !error && hasAny && (
          <button
            onClick={handleShowMore}
            disabled={loadingMore}
            className="w-full py-2 text-xs font-semibold text-[var(--scu-red)] hover:bg-red-50 rounded-lg transition disabled:opacity-50"
          >
            {loadingMore ? "Loading…" : "Show more ↓"}
          </button>
        )}
      </div>
    </div>
  );
}

function CandidateCard({
  c,
  onAdd,
  addDisabled,
  badgeClass,
}: {
  c: CourseSuggestion;
  onAdd: () => void;
  addDisabled?: boolean;
  badgeClass: string;
}) {
  return (
    <div className="rounded-lg border border-neutral-200 bg-white hover:border-neutral-300 transition overflow-hidden">
      <div className="flex items-start gap-2 px-3 py-2">
        <div className="flex-1 min-w-0">
          <p className="text-xs font-bold text-neutral-900 leading-tight">{c.course}</p>
          <p className="text-[11px] text-neutral-600 leading-tight truncate">{c.title}</p>
          {Array.isArray(c.covers) && c.covers.length > 0 && (
            <div className="mt-1 flex flex-wrap items-center gap-1">
              <span className="text-[10px] font-semibold text-neutral-500 shrink-0">Covers:</span>
              {c.covers.slice(0, 2).map((t) => (
                <span
                  key={t}
                  className={`inline-flex items-center rounded-full text-[10px] font-semibold px-2 py-0.5 border ${badgeClass}`}
                >
                  {t}
                </span>
              ))}
            </div>
          )}
          <p className="text-[11px] text-neutral-400 mt-0.5 flex flex-wrap items-center gap-1.5">
            <StarIcon />
            <span>{c.rating.toFixed(1)}</span>
            <span className="text-neutral-300">·</span>
            <span>{c.units}u</span>
            <span className="text-neutral-300">·</span>
            <span className="truncate" title={c.instructor}>
              {c.instructor}
            </span>
          </p>
          <p className="text-[10px] text-neutral-500 mt-1 leading-snug">{c.rationale}</p>
        </div>
        <button
          type="button"
          onClick={onAdd}
          disabled={addDisabled}
          title={addDisabled ? "This requirement is already satisfied (usually one course is enough)" : undefined}
          className={`shrink-0 px-2.5 py-1.5 text-[11px] font-bold rounded-md transition ${
            addDisabled
              ? "bg-neutral-200 text-neutral-500 cursor-not-allowed"
              : "bg-[var(--scu-red)] text-white hover:bg-red-700"
          }`}
        >
          {addDisabled ? "Satisfied" : "Add"}
        </button>
      </div>
    </div>
  );
}

function isAlreadySatisfied(c: CourseSuggestion, satisfied: string[]): boolean {
  if (!Array.isArray(c.covers) || c.covers.length === 0) return false;
  if (!Array.isArray(satisfied) || satisfied.length === 0) return false;
  const sat = new Set(satisfied.map((x) => String(x || "").trim()).filter(Boolean));
  // If any cover label is already satisfied, treat this as duplicative.
  return c.covers.some((lab) => sat.has(String(lab || "").trim()));
}

function XIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" aria-hidden>
      <path d="M18 6L6 18M6 6l12 12" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" />
    </svg>
  );
}

function StarIcon() {
  return (
    <svg width="10" height="10" viewBox="0 0 24 24" fill="currentColor" className="text-amber-400 shrink-0" aria-hidden>
      <path d="M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01L12 2z" />
    </svg>
  );
}
