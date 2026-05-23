/**
 * R6 — Calendar slot-click suggestion popover.
 *
 * Appears anchored near the clicked calendar cell and shows 3-5 candidate
 * courses ranked by fit. No chat round-trip — "Add to plan" writes directly
 * to planResult.recommended via the onAddCourse callback.
 */

import { useCallback, useEffect, useRef, useState } from "react";

const API_BASE = import.meta.env.VITE_API_BASE ?? "";

export interface SlotCandidate {
  course: string;
  title: string;
  professor: string;
  rating: number | null;
  units: number | null;
  meeting_days: number[];
  meeting_start_min: number | null;
  meeting_end_min: number | null;
  rationale: string;
}

export interface SlotPopoverState {
  day: number;       // 0 = Mon … 4 = Fri
  startMin: number;  // minutes from 8 AM
  rect: DOMRect;     // bounding rect of the clicked cell
}

interface Props {
  state: SlotPopoverState;
  missingDetails: Record<string, unknown>[];
  userId: string;
  /** Codes already on the calendar — excluded from suggestions automatically */
  existingCodes: string[];
  onAddCourse: (candidate: SlotCandidate) => void;
  onClose: () => void;
}

const DAY_LABELS = ["Mon", "Tue", "Wed", "Thu", "Fri"];

function timeLabel(minutesFrom8am: number): string {
  const total = 8 * 60 + minutesFrom8am;
  const h = Math.floor(total / 60);
  const m = total % 60;
  const suffix = h < 12 ? "AM" : "PM";
  const h12 = h % 12 || 12;
  return `${h12}:${String(m).padStart(2, "0")} ${suffix}`;
}

function StarRating({ rating }: { rating: number | null }) {
  if (rating === null) return <span className="text-[10px] text-neutral-400">No rating</span>;
  const filled = Math.round(rating);
  return (
    <span className="flex items-center gap-0.5" title={`${rating.toFixed(1)} / 5`}>
      {[1, 2, 3, 4, 5].map((i) => (
        <svg key={i} width="9" height="9" viewBox="0 0 24 24" fill={i <= filled ? "#f59e0b" : "none"} stroke="#f59e0b" strokeWidth="2">
          <polygon points="12,2 15.09,8.26 22,9.27 17,14.14 18.18,21.02 12,17.77 5.82,21.02 7,14.14 2,9.27 8.91,8.26" />
        </svg>
      ))}
      <span className="ml-0.5 text-[10px] text-neutral-500">{rating.toFixed(1)}</span>
    </span>
  );
}

export function SlotSuggestionPopover({
  state,
  missingDetails,
  userId,
  existingCodes,
  onAddCourse,
  onClose,
}: Props) {
  const [candidates, setCandidates] = useState<SlotCandidate[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expandedIdx, setExpandedIdx] = useState<number | null>(null);
  const [excludeCodes, setExcludeCodes] = useState<string[]>([...existingCodes]);
  const [addedCodes, setAddedCodes] = useState<Set<string>>(new Set());
  const popoverRef = useRef<HTMLDivElement>(null);

  const fetchCandidates = useCallback(
    async (exclude: string[]) => {
      setLoading(true);
      setError(null);
      try {
        const res = await fetch(`${API_BASE}/api/plan/suggest_for_slot`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            day: state.day,
            start_min: state.startMin,
            end_min: state.startMin + 30,
            missing_details: missingDetails,
            user_id: userId,
            exclude_codes: exclude,
          }),
        });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = (await res.json()) as { candidates: SlotCandidate[] };
        setCandidates(data.candidates ?? []);
      } catch (e) {
        setError("Couldn't load suggestions. Try again.");
        setCandidates([]);
      } finally {
        setLoading(false);
      }
    },
    [state.day, state.startMin, missingDetails, userId],
  );

  // Fetch on mount
  useEffect(() => {
    void fetchCandidates(excludeCodes);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Close on outside click
  useEffect(() => {
    function handleMouseDown(e: MouseEvent) {
      if (popoverRef.current && !popoverRef.current.contains(e.target as Node)) {
        onClose();
      }
    }
    document.addEventListener("mousedown", handleMouseDown);
    return () => document.removeEventListener("mousedown", handleMouseDown);
  }, [onClose]);

  // Close on Escape
  useEffect(() => {
    function handleKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    document.addEventListener("keydown", handleKey);
    return () => document.removeEventListener("keydown", handleKey);
  }, [onClose]);

  // Position: anchor to the right of the cell, fall back to left if too close to right edge
  const { rect } = state;
  const POPOVER_W = 300;
  const left =
    rect.right + POPOVER_W + 8 < window.innerWidth
      ? rect.right + 8
      : rect.left - POPOVER_W - 8;
  const top = Math.min(rect.top, window.innerHeight - 420);

  function handleAdd(c: SlotCandidate) {
    onAddCourse(c);
    setAddedCodes((prev) => new Set([...prev, c.course]));
  }

  function handleShowMore() {
    const nowExclude = [...excludeCodes, ...candidates.map((c) => c.course)];
    setExcludeCodes(nowExclude);
    setExpandedIdx(null);
    void fetchCandidates(nowExclude);
  }

  return (
    <div
      ref={popoverRef}
      style={{ position: "fixed", top, left, width: POPOVER_W, zIndex: 9999 }}
      className="rounded-xl border border-neutral-200 bg-white shadow-2xl ring-1 ring-black/5 overflow-hidden"
    >
      {/* Header */}
      <div className="flex items-center justify-between border-b border-neutral-100 bg-neutral-50 px-3 py-2">
        <span className="text-xs font-semibold text-[var(--scu-text)]">
          {DAY_LABELS[state.day]} · {timeLabel(state.startMin)}
        </span>
        <button
          type="button"
          onClick={onClose}
          className="rounded p-0.5 text-neutral-400 hover:text-neutral-700 hover:bg-neutral-200 transition"
          aria-label="Close"
        >
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round">
            <path d="M18 6L6 18M6 6l12 12" />
          </svg>
        </button>
      </div>

      {/* Body */}
      <div className="max-h-[360px] overflow-y-auto divide-y divide-neutral-100">
        {loading && (
          <div className="flex items-center justify-center py-8 gap-2 text-neutral-400 text-xs">
            <svg className="animate-spin" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M21 12a9 9 0 1 1-6.22-8.56" />
            </svg>
            Finding courses…
          </div>
        )}

        {!loading && error && (
          <p className="px-3 py-4 text-xs text-red-500">{error}</p>
        )}

        {!loading && !error && candidates.length === 0 && (
          <p className="px-3 py-4 text-xs text-neutral-400">
            No courses available at this time slot.
          </p>
        )}

        {!loading && !error &&
          candidates.map((c, i) => {
            const isExpanded = expandedIdx === i;
            const isAdded = addedCodes.has(c.course);
            return (
              <div key={c.course} className="px-3 py-2.5">
                {/* Row: code + add button */}
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0 flex-1">
                    <p className="text-xs font-bold text-[var(--scu-text)] leading-tight">{c.course}</p>
                    {c.title && (
                      <p className="truncate text-[11px] text-neutral-500 leading-tight mt-0.5">{c.title}</p>
                    )}
                    <div className="flex items-center gap-2 mt-1 flex-wrap">
                      {c.professor && (
                        <span className="text-[10px] text-neutral-500">{c.professor}</span>
                      )}
                      <StarRating rating={c.rating} />
                      {c.units != null && (
                        <span className="text-[10px] text-neutral-400">{c.units} units</span>
                      )}
                    </div>
                    {c.meeting_start_min != null && c.meeting_end_min != null && (
                      <p className="text-[10px] text-neutral-400 mt-0.5">
                        {timeLabel(c.meeting_start_min)} – {timeLabel(c.meeting_end_min)}
                      </p>
                    )}
                  </div>
                  <button
                    type="button"
                    onClick={() => !isAdded && handleAdd(c)}
                    disabled={isAdded}
                    className={`shrink-0 rounded-md px-2.5 py-1 text-[11px] font-semibold transition ${
                      isAdded
                        ? "bg-green-50 text-green-600 cursor-default"
                        : "bg-[var(--scu-red)] text-white hover:opacity-90 active:opacity-80"
                    }`}
                  >
                    {isAdded ? "✓ Added" : "Add"}
                  </button>
                </div>

                {/* Why this? toggle */}
                {c.rationale && (
                  <button
                    type="button"
                    onClick={() => setExpandedIdx(isExpanded ? null : i)}
                    className="mt-1.5 text-[10px] text-[var(--scu-red)] hover:underline flex items-center gap-0.5"
                  >
                    <svg
                      width="10"
                      height="10"
                      viewBox="0 0 24 24"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth="2.5"
                      className={`transition-transform ${isExpanded ? "rotate-180" : ""}`}
                    >
                      <path d="M6 9l6 6 6-6" />
                    </svg>
                    Why this?
                  </button>
                )}
                {isExpanded && c.rationale && (
                  <p className="mt-1 text-[10px] text-neutral-500 leading-snug bg-neutral-50 rounded px-2 py-1">
                    {c.rationale}
                  </p>
                )}
              </div>
            );
          })}
      </div>

      {/* Show more */}
      {!loading && candidates.length > 0 && (
        <div className="border-t border-neutral-100 px-3 py-2">
          <button
            type="button"
            onClick={handleShowMore}
            className="w-full text-center text-[11px] text-neutral-400 hover:text-[var(--scu-red)] transition"
          >
            Show more options →
          </button>
        </div>
      )}
    </div>
  );
}
