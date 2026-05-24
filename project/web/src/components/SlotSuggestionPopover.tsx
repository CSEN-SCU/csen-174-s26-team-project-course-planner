import { useEffect, useRef, useState } from "react";
import { suggestCoursesForSlot, type CourseSuggestion } from "../api/client";

export type SlotSuggestionPopoverProps = {
  day_index: number;
  slot_index: number;
  start_min: number;
  end_min: number;
  missing_details: Record<string, unknown>[];
  excluded_courses: string[];
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
  onAddCourse,
  onClose,
  client_x,
  client_y,
}: SlotSuggestionPopoverProps) {
  const [candidates, setCandidates] = useState<CourseSuggestion[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [expandedIdx, setExpandedIdx] = useState<number | null>(null);
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
    suggestCoursesForSlot({
      day_index,
      start_min,
      end_min,
      missing_details,
      exclude_codes: excluded_courses,
    })
      .then((res) => {
        setCandidates(res.candidates);
        setShownCodes([...excluded_courses, ...res.candidates.map((c) => c.course)]);
      })
      .catch((err) => {
        setError(err instanceof Error ? err.message : "Failed to load suggestions");
      })
      .finally(() => {
        setLoading(false);
      });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [day_index, start_min, end_min]);

  const handleAddCourse = (candidate: CourseSuggestion) => {
    onAddCourse({
      course: candidate.course,
      title: candidate.title,
      units: candidate.units,
      category: "", // filled by caller based on missing_details
      reason: candidate.rationale,
      instructor: candidate.instructor,
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
    })
      .then((res) => {
        if (res.candidates.length === 0) return; // nothing new
        setCandidates((prev) => [...prev, ...res.candidates]);
        setShownCodes((prev) => [...prev, ...res.candidates.map((c) => c.course)]);
      })
      .catch(() => {/* silent — best effort */})
      .finally(() => setLoadingMore(false));
  };

  const dayNames = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
  const hour = Math.floor(start_min / 60);
  const min = start_min % 60;
  const timeStr = `${hour % 12 || 12}:${String(min).padStart(2, "0")} ${hour < 12 ? "AM" : "PM"}`;

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

        {/* Empty */}
        {!loading && !error && candidates.length === 0 && (
          <p className="text-xs text-neutral-400 text-center py-4">
            No courses available at this time slot.
          </p>
        )}

        {/* Candidate cards */}
        {!loading && !error && candidates.map((c, idx) => (
          <div
            key={c.course}
            className="rounded-lg border border-neutral-200 bg-white hover:border-neutral-300 transition overflow-hidden"
          >
            {/* Summary row */}
            <div className="flex items-start gap-2 px-3 py-2">
              <div className="flex-1 min-w-0">
                <p className="text-xs font-bold text-neutral-900 leading-tight">
                  {c.course}
                </p>
                <p className="text-[11px] text-neutral-600 leading-tight truncate">
                  {c.title}
                </p>
                <p className="text-[11px] text-neutral-400 mt-0.5 flex items-center gap-1.5">
                  <StarIcon />
                  <span>{c.rating.toFixed(1)}</span>
                  <span className="text-neutral-300">·</span>
                  <span>{c.instructor}</span>
                  <span className="text-neutral-300">·</span>
                  <span>{c.units}u</span>
                </p>
              </div>
              <button
                onClick={() => handleAddCourse(c)}
                className="shrink-0 px-2.5 py-1.5 text-[11px] font-bold bg-[var(--scu-red)] text-white rounded-md hover:bg-red-700 transition"
              >
                Add
              </button>
            </div>

            {/* Expandable rationale */}
            {expandedIdx === idx && (
              <div className="px-3 pb-2 pt-1 border-t border-neutral-100 bg-neutral-50">
                <p className="text-[11px] text-neutral-700 leading-relaxed">{c.rationale}</p>
                <p className="text-[10px] text-neutral-500 mt-1">
                  Difficulty: {c.difficulty.toFixed(1)} / 5
                </p>
              </div>
            )}

            {/* "Why this?" toggle */}
            <button
              onClick={() => setExpandedIdx(expandedIdx === idx ? null : idx)}
              className="w-full text-left px-3 pb-2 text-[11px] text-[var(--scu-red)] hover:underline"
            >
              {expandedIdx === idx ? "Hide details ▲" : "Why this? ▼"}
            </button>
          </div>
        ))}

        {/* Show more */}
        {!loading && !error && candidates.length > 0 && (
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
