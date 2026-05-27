import { useEffect, useMemo, useState } from "react";
import { searchCatalogSections, type CatalogSection } from "../api/client";
import { InstructorRatingLine } from "./InstructorRatingLine";

type CourseSwapModalProps = {
  open: boolean;
  courseCode: string;
  currentSection?: number;
  onClose: () => void;
  onRemove: () => void;
  onSwap: (section: CatalogSection) => void;
};

function normalizeCourse(code: string): string {
  return code.trim().toUpperCase();
}

export function CourseSwapModal({
  open,
  courseCode,
  currentSection,
  onClose,
  onRemove,
  onSwap,
}: CourseSwapModalProps) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sections, setSections] = useState<CatalogSection[]>([]);

  useEffect(() => {
    if (!open) return;
    const target = normalizeCourse(courseCode);
    if (!target) return;
    setLoading(true);
    setError(null);
    void searchCatalogSections({ q: target, limit: 300, sort: "rating" })
      .then((res) => {
        const sameCourse = (res.sections ?? []).filter(
          (s) => normalizeCourse(s.course) === target,
        );
        setSections(sameCourse);
      })
      .catch((e) => setError(e instanceof Error ? e.message : String(e)))
      .finally(() => setLoading(false));
  }, [open, courseCode]);

  const alternatives = useMemo(
    () => sections.filter((s) => s.section !== currentSection),
    [sections, currentSection],
  );

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-[90] flex items-center justify-center bg-black/40 p-4">
      <div
        className="fixed inset-0"
        aria-hidden
        onClick={onClose}
      />
      <section
        role="dialog"
        aria-modal="true"
        aria-labelledby="swap-course-title"
        className="relative z-10 w-full max-w-xl rounded-lg border border-neutral-200 bg-white shadow-xl"
      >
        <header className="flex items-start justify-between border-b border-neutral-200 px-4 py-3">
          <div>
            <h2 id="swap-course-title" className="text-sm font-semibold text-[var(--scu-text)]">
              Edit {courseCode}
            </h2>
            <p className="mt-0.5 text-xs text-neutral-500">
              Swap to another section (time/professor) or remove this course.
            </p>
          </div>
          <button
            type="button"
            className="rounded px-2 py-1 text-neutral-500 hover:bg-neutral-100"
            onClick={onClose}
            aria-label="Close"
          >
            ✕
          </button>
        </header>

        <div className="max-h-[60vh] overflow-y-auto p-4">
          {loading && <p className="text-sm text-neutral-500">Loading sections…</p>}
          {error && <p className="text-sm text-red-600">{error}</p>}
          {!loading && !error && alternatives.length === 0 && (
            <p className="text-sm text-neutral-500">No alternate sections found for this course.</p>
          )}
          {!loading && !error && alternatives.length > 0 && (
            <ul className="space-y-2">
              {alternatives.map((sec) => (
                <li key={`${sec.course}-${sec.section}`}>
                  <button
                    type="button"
                    onClick={() => onSwap(sec)}
                    className="w-full rounded-md border border-neutral-200 bg-white px-3 py-2 text-left transition hover:border-[var(--scu-red)] hover:bg-red-50"
                  >
                    <div className="flex items-center justify-between gap-2">
                      <span className="text-sm font-semibold text-[var(--scu-text)]">
                        Section {sec.section}
                      </span>
                      {sec.status && (
                        <span className="rounded bg-neutral-100 px-1.5 py-0.5 text-[10px] text-neutral-600">
                          {sec.status}
                        </span>
                      )}
                    </div>
                    <p className="mt-1 text-xs text-neutral-600">
                      {(sec.instructors ?? []).join(", ") || "TBA"}
                    </p>
                    <InstructorRatingLine section={sec} className="mt-1" />
                    <p className="mt-0.5 text-xs text-neutral-500">
                      {sec.meeting_pattern || "Time not posted"}
                    </p>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>

        <footer className="flex items-center justify-between border-t border-neutral-200 px-4 py-3">
          <button
            type="button"
            onClick={onRemove}
            className="rounded-md border border-red-200 bg-red-50 px-3 py-1.5 text-xs font-semibold text-red-700 transition hover:bg-red-100"
          >
            Remove from schedule
          </button>
          <button
            type="button"
            onClick={onClose}
            className="rounded-md border border-neutral-300 bg-white px-3 py-1.5 text-xs font-semibold text-neutral-700 transition hover:bg-neutral-100"
          >
            Cancel
          </button>
        </footer>
      </section>
    </div>
  );
}
