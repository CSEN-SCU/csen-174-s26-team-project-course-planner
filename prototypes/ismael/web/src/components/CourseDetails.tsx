import type { CourseResult } from "../types/domain";
import { cn } from "../lib/ui";

export function CourseDetails({
  selectedCourse,
  selectedSectionId,
  onSelectSection,
  onAdd
}: {
  selectedCourse: CourseResult | null;
  selectedSectionId: string;
  onSelectSection: (id: string) => void;
  onAdd: () => void;
}) {
  return (
    <article className="glass rounded-2xl p-4">
      <h3 className="text-lg text-white">Course details</h3>
      {!selectedCourse ? (
        <p className="mt-3 text-sm text-slate-300">Select a course row to choose section, time, and professor.</p>
      ) : (
        <div className="mt-3 space-y-3">
          <div>
            <p className="font-semibold text-sky-100">
              {selectedCourse.code} · {selectedCourse.name}
            </p>
            <p className="text-xs text-slate-300">
              Type: {selectedCourse.type} · Division: {selectedCourse.division}
            </p>
          </div>
          <div className="space-y-2">
            {selectedCourse.sections.map((section) => (
              <button
                key={section.id}
                onClick={() => onSelectSection(section.id)}
                className={cn(
                  "w-full rounded-lg border p-3 text-left text-xs",
                  selectedSectionId === section.id ? "border-sky-300 bg-sky-300/15" : "border-slate-600 bg-slate-900/30"
                )}
              >
                <p className="font-semibold text-slate-100">
                  {section.days} {section.time} · {section.instructor}
                </p>
                <p className="mt-1 text-slate-300">
                  Quality {section.quality.toFixed(1)} · Difficulty {section.difficulty.toFixed(1)}
                </p>
              </button>
            ))}
          </div>
          <button
            onClick={onAdd}
            disabled={!selectedSectionId}
            className="w-full rounded-lg bg-mint/90 px-3 py-2 text-sm font-semibold text-slate-950 disabled:opacity-60"
          >
            Add to schedule
          </button>
        </div>
      )}
    </article>
  );
}

