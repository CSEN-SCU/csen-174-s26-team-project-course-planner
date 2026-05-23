import React, { useEffect, useState } from "react";
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
  /* Position in pixels from top-left of calendar container */
  top_px: number;
  left_px: number;
};

export function SlotSuggestionPopover({
  day_index,
  slot_index,
  start_min,
  end_min,
  missing_details,
  excluded_courses,
  onAddCourse,
  onClose,
  top_px,
  left_px,
}: SlotSuggestionPopoverProps) {
  const [candidates, setCandidates] = useState<CourseSuggestion[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expandedIdx, setExpandedIdx] = useState<number | null>(null);

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
      })
      .catch((err) => {
        setError(err instanceof Error ? err.message : "Failed to load suggestions");
      })
      .finally(() => {
        setLoading(false);
      });
  }, [day_index, start_min, end_min, missing_details, excluded_courses]);

  const handleAddCourse = (candidate: CourseSuggestion) => {
    onAddCourse({
      course: candidate.course,
      title: candidate.title,
      units: candidate.units,
      category: "", // Will be filled by caller based on missing_details
      reason: candidate.rationale,
      instructor: candidate.instructor,
    });
    onClose();
  };

  const dayNames = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
  const timeStr = `${Math.floor(start_min / 60)}:${String(start_min % 60).padStart(2, "0")}`;

  return (
    <div
      className="fixed z-50 bg-white rounded-lg shadow-lg border border-neutral-200 p-4 max-w-sm"
      style={{ top: `${top_px}px`, left: `${left_px}px`, maxHeight: "400px", overflowY: "auto" }}
      onClick={(e) => e.stopPropagation()}
    >
      {/* Header */}
      <div className="flex items-center justify-between mb-3 pb-2 border-b">
        <h3 className="text-sm font-semibold text-neutral-800">
          Courses for {dayNames[day_index]} at {timeStr}
        </h3>
        <button
          onClick={onClose}
          className="text-neutral-400 hover:text-neutral-600"
          aria-label="Close"
        >
          ✕
        </button>
      </div>

      {/* Loading */}
      {loading && <div className="text-xs text-neutral-500 py-2">Loading suggestions...</div>}

      {/* Error */}
      {error && (
        <div className="text-xs text-red-600 py-2 bg-red-50 px-2 rounded">
          {error}
        </div>
      )}

      {/* Candidates */}
      {!loading && !error && candidates.length === 0 && (
        <div className="text-xs text-neutral-500 py-3">No matching courses at this time.</div>
      )}

      {!loading && !error && candidates.length > 0 && (
        <div className="space-y-2">
          {candidates.map((c, idx) => (
            <div key={c.course} className="border border-neutral-200 rounded-lg p-2 hover:bg-neutral-50">
              {/* Summary row */}
              <div className="flex items-start justify-between gap-2">
                <div className="flex-1 min-w-0">
                  <p className="text-xs font-semibold text-neutral-900 truncate">
                    {c.course}
                  </p>
                  <p className="text-xs text-neutral-600 truncate">
                    {c.title}
                  </p>
                  <p className="text-xs text-neutral-500 mt-0.5">
                    {c.units} units • {c.instructor} ({c.rating.toFixed(1)})
                  </p>
                </div>
                <button
                  onClick={() => handleAddCourse(c)}
                  className="shrink-0 px-2 py-1 text-xs font-semibold bg-[var(--scu-red)] text-white rounded hover:opacity-90"
                >
                  Add
                </button>
              </div>

              {/* Expandable rationale */}
              {expandedIdx === idx && (
                <div className="mt-2 pt-2 border-t border-neutral-200">
                  <p className="text-xs text-neutral-700">{c.rationale}</p>
                  <p className="text-xs text-neutral-500 mt-1">
                    Difficulty: {c.difficulty.toFixed(1)}/5
                  </p>
                </div>
              )}

              {/* Toggle rationale button */}
              <button
                onClick={() => setExpandedIdx(expandedIdx === idx ? null : idx)}
                className="text-xs text-[var(--scu-red)] hover:underline mt-1"
              >
                {expandedIdx === idx ? "Hide details" : "Why this?"}
              </button>
            </div>
          ))}
        </div>
      )}

      {/* Footer */}
      {!loading && !error && candidates.length > 0 && (
        <div className="text-xs text-neutral-500 mt-3 pt-2 border-t">
          Showing {candidates.length} suggestion{candidates.length > 1 ? "s" : ""}
        </div>
      )}
    </div>
  );
}
