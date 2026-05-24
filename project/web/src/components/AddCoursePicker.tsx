import { useEffect, useMemo, useRef, useState } from "react";
import { listCourses, type OfferedCourse } from "../api/client";

export type AddCoursePickerProps = {
  /** Course codes already in the plan (to disable / mark as added). */
  existingCodes: string[];
  /** Receives the picked course plus its lab co-requisite (if offered + not
   *  already in the plan) — SCU lecture+lab pairs are added together. */
  onAdd: (courses: OfferedCourse[]) => void;
};

/**
 * "+ Add course" control: a button that opens a searchable dropdown of
 * next-term courses (fetched once). Selecting one adds it directly to the
 * plan — no AI round-trip — like the original prototype's manual builder.
 */
export function AddCoursePicker({ existingCodes, onAdd }: AddCoursePickerProps) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [courses, setCourses] = useState<OfferedCourse[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const boxRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const existing = useMemo(
    () => new Set(existingCodes.map((c) => c.trim().toUpperCase())),
    [existingCodes],
  );

  // Fetch the catalog the first time the dropdown opens.
  useEffect(() => {
    if (!open || courses !== null) return;
    setLoading(true);
    setError(null);
    listCourses()
      .then((cs) => setCourses(cs))
      .catch((e) => setError(e instanceof Error ? e.message : "Failed to load courses"))
      .finally(() => setLoading(false));
  }, [open, courses]);

  // Focus the search input when opening.
  useEffect(() => {
    if (open) setTimeout(() => inputRef.current?.focus(), 0);
  }, [open]);

  // Close on outside click.
  useEffect(() => {
    if (!open) return;
    const onDocClick = (e: MouseEvent) => {
      if (boxRef.current && !boxRef.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onDocClick);
    return () => document.removeEventListener("mousedown", onDocClick);
  }, [open]);

  const filtered = useMemo(() => {
    if (!courses) return [];
    const q = query.trim().toLowerCase();
    if (!q) return []; // show hint instead of unfiltered list
    return courses
      .filter(
        (c) =>
          c.course.toLowerCase().includes(q) ||
          (c.title ?? "").toLowerCase().includes(q),
      )
      .slice(0, 50); // cap the rendered list for performance
  }, [courses, query]);

  return (
    <div ref={boxRef} className="relative">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="flex items-center gap-1 rounded-md border border-[var(--scu-red)] px-2.5 py-1 text-xs font-semibold text-[var(--scu-red)] transition hover:bg-red-50"
      >
        <span className="text-sm leading-none">+</span> Add course
      </button>

      {open && (
        <div className="absolute right-0 z-20 mt-1 w-80 rounded-md border border-neutral-200 bg-white shadow-lg">
          <div className="border-b border-neutral-100 p-2">
            <input
              ref={inputRef}
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search by code or title (e.g. CSEN 174)…"
              className="w-full rounded border border-neutral-300 px-2 py-1.5 text-xs outline-none focus:border-[var(--scu-red)] focus:ring-1 focus:ring-[var(--scu-red)]"
            />
          </div>
          <div className="max-h-72 overflow-y-auto">
            {loading && <p className="p-3 text-xs text-neutral-400">Loading courses…</p>}
            {error && <p className="p-3 text-xs text-red-600">{error}</p>}
            {!loading && !error && query.trim() === "" && (
              <p className="p-3 text-xs text-neutral-400">
                Type a course code or name to search {courses ? `(${courses.length} courses)` : ""}…
              </p>
            )}
            {!loading && !error && query.trim() !== "" && filtered.length === 0 && (
              <p className="p-3 text-xs text-neutral-400">No matching courses.</p>
            )}
            {!loading &&
              !error &&
              filtered.map((c) => {
                const added = existing.has(c.course.toUpperCase());
                return (
                  <button
                    key={c.course}
                    type="button"
                    disabled={added}
                    onClick={() => {
                      const additions: OfferedCourse[] = [c];
                      // Co-requisite: pull in the lab partner too (if offered
                      // and not already in the plan).
                      if (c.lab_partner) {
                        const lab = (courses ?? []).find(
                          (x) => x.course.toUpperCase() === c.lab_partner!.toUpperCase(),
                        );
                        if (lab && !existing.has(lab.course.toUpperCase())) {
                          additions.push(lab);
                        }
                      }
                      onAdd(additions);
                      setOpen(false);
                      setQuery("");
                    }}
                    className={`flex w-full items-start justify-between gap-2 border-b border-neutral-50 px-3 py-2 text-left transition last:border-0 ${
                      added ? "cursor-default opacity-40" : "hover:bg-red-50/60"
                    }`}
                  >
                    <span className="min-w-0">
                      <span className="block text-xs font-semibold text-[var(--scu-text)]">
                        {c.course}
                        {c.lab_partner && (
                          <span className="ml-1 font-normal text-[10px] text-neutral-400">
                            + lab
                          </span>
                        )}
                      </span>
                      {c.title && (
                        <span className="block truncate text-[10px] text-neutral-500">
                          {c.title}
                        </span>
                      )}
                    </span>
                    <span className="shrink-0 text-[10px] text-neutral-400">
                      {added ? "added" : c.units != null ? `${c.units}u` : ""}
                    </span>
                  </button>
                );
              })}
          </div>
        </div>
      )}
    </div>
  );
}
