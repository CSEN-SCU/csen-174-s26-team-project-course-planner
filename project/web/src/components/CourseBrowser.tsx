import { useCallback, useEffect, useMemo, useState } from "react";
import {
  searchCatalogSections,
  type CatalogSection,
  type CourseBrowserLaunchContext,
} from "../api/client";
import { WEEKDAY_LABELS } from "../types";

export type CourseBrowserAddOptions = {
  slotAnchor?: {
    dayIndex: number;
    startMin: number;
    endMin: number;
  };
};

export type CourseBrowserProps = {
  open: boolean;
  context: CourseBrowserLaunchContext;
  existingCodes: string[];
  onAdd: (sections: CatalogSection[], options?: CourseBrowserAddOptions) => void;
  onClose: () => void;
};

const DAY_OPTIONS = [0, 1, 2, 3, 4] as const;

export function CourseBrowser({
  open,
  context,
  existingCodes,
  onAdd,
  onClose,
}: CourseBrowserProps) {
  const [query, setQuery] = useState("");
  const [subjects, setSubjects] = useState<string[]>([]);
  const [days, setDays] = useState<number[]>([]);
  const [timeBuckets, setTimeBuckets] = useState<string[]>([]);
  const [tags, setTags] = useState<string[]>([]);
  const [sections, setSections] = useState<CatalogSection[]>([]);
  const [total, setTotal] = useState(0);
  const [facets, setFacets] = useState<{
    subjects: string[];
    tags: { Core: string[]; Other: string[] };
    time_buckets: string[];
  } | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [slotFilterActive, setSlotFilterActive] = useState(context.mode === "slot");

  const existing = useMemo(
    () => new Set(existingCodes.map((c) => c.trim().toUpperCase())),
    [existingCodes],
  );

  const slotParams = useMemo(() => {
    if (context.mode !== "slot" || !slotFilterActive) return {};
    return {
      day_index: context.dayIndex,
      start_min: context.startMin,
      end_min: context.endMin,
    };
  }, [context, slotFilterActive]);

  const fetchSections = useCallback(async () => {
    if (!open) return;
    setLoading(true);
    setError(null);
    try {
      const data = await searchCatalogSections({
        q: query || undefined,
        subject: subjects.length ? subjects : undefined,
        days: days.length ? days : undefined,
        time_bucket: timeBuckets.length ? timeBuckets : undefined,
        tag: tags.length ? tags : undefined,
        limit: 100,
        ...slotParams,
      });
      setSections(data.sections);
      setTotal(data.total);
      setFacets(data.facets);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setSections([]);
      setTotal(0);
    } finally {
      setLoading(false);
    }
  }, [open, query, subjects, days, timeBuckets, tags, slotParams]);

  useEffect(() => {
    if (!open) return;
    const t = window.setTimeout(() => void fetchSections(), 300);
    return () => window.clearTimeout(t);
  }, [open, fetchSections]);

  useEffect(() => {
    if (open && context.mode === "slot") {
      setSlotFilterActive(true);
      setDays([context.dayIndex]);
    }
  }, [open, context]);

  if (!open) return null;

  const toggleInList = <T,>(list: T[], item: T, set: (v: T[]) => void) => {
    set(list.includes(item) ? list.filter((x) => x !== item) : [...list, item]);
  };

  const handleAdd = (sec: CatalogSection) => {
    const additions: CatalogSection[] = [sec];
    if (sec.lab_partner) {
      const lab = sections.find(
        (s) => s.course.toUpperCase() === sec.lab_partner!.toUpperCase(),
      );
      if (lab && !existing.has(lab.course.toUpperCase())) {
        additions.push(lab);
      }
    }
    const anchor =
      context.mode === "slot" && slotFilterActive
        ? {
            dayIndex: context.dayIndex,
            startMin: context.startMin,
            endMin: context.endMin,
          }
        : undefined;
    onAdd(additions, anchor ? { slotAnchor: anchor } : undefined);
    onClose();
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-2 sm:p-4"
      role="dialog"
      aria-modal="true"
      aria-labelledby="course-browser-title"
    >
      <div className="flex h-[min(90vh,720px)] w-full max-w-5xl flex-col overflow-hidden rounded-lg bg-white shadow-xl ring-1 ring-neutral-200">
        <header className="flex shrink-0 items-start justify-between gap-3 border-b border-neutral-200 px-4 py-3">
          <div>
            <h2 id="course-browser-title" className="text-base font-semibold text-[var(--scu-text)]">
              Browse courses
            </h2>
            {context.mode === "slot" && slotFilterActive && (
              <p className="mt-1 text-xs text-[var(--scu-red)]">
                {context.label} — showing sections that overlap this time
                <button
                  type="button"
                  className="ml-2 underline"
                  onClick={() => setSlotFilterActive(false)}
                >
                  Clear time filter
                </button>
              </p>
            )}
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded px-2 py-1 text-neutral-500 hover:bg-neutral-100"
            aria-label="Close"
          >
            ✕
          </button>
        </header>

        <div className="flex min-h-0 flex-1">
          <aside className="w-52 shrink-0 overflow-y-auto border-r border-neutral-100 bg-neutral-50 p-3 text-xs">
            <p className="mb-2 font-semibold text-neutral-700">Filters</p>
            <p className="mb-1 text-neutral-500">Meeting days</p>
            <div className="mb-3 flex flex-wrap gap-1">
              {DAY_OPTIONS.map((d) => (
                <button
                  key={d}
                  type="button"
                  onClick={() => toggleInList(days, d, setDays)}
                  className={`rounded px-2 py-0.5 ${
                    days.includes(d)
                      ? "bg-[var(--scu-red)] text-white"
                      : "bg-white ring-1 ring-neutral-200"
                  }`}
                >
                  {WEEKDAY_LABELS[d]}
                </button>
              ))}
            </div>
            <p className="mb-1 text-neutral-500">Time of day</p>
            <div className="mb-3 flex flex-col gap-1">
              {(facets?.time_buckets ?? ["morning", "afternoon", "evening"]).map((b) => (
                <label key={b} className="flex items-center gap-1.5 capitalize">
                  <input
                    type="checkbox"
                    checked={timeBuckets.includes(b)}
                    onChange={() => toggleInList(timeBuckets, b, setTimeBuckets)}
                  />
                  {b}
                </label>
              ))}
            </div>
            {facets?.tags?.Core && facets.tags.Core.length > 0 && (
              <>
                <p className="mb-1 text-neutral-500">Core requirements</p>
                <div className="mb-3 max-h-32 overflow-y-auto space-y-0.5">
                  {facets.tags.Core.map((t) => (
                    <label key={t} className="flex items-center gap-1.5">
                      <input
                        type="checkbox"
                        checked={tags.includes(t)}
                        onChange={() => toggleInList(tags, t, setTags)}
                      />
                      <span className="truncate">{t}</span>
                    </label>
                  ))}
                </div>
              </>
            )}
            {facets?.subjects && facets.subjects.length > 0 && (
              <>
                <p className="mb-1 text-neutral-500">Subject</p>
                <select
                  multiple
                  className="mb-2 h-24 w-full rounded border border-neutral-200 text-[10px]"
                  value={subjects}
                  onChange={(e) => {
                    const opts = Array.from(e.target.selectedOptions).map((o) => o.value);
                    setSubjects(opts);
                  }}
                >
                  {facets.subjects.map((s) => (
                    <option key={s} value={s}>
                      {s}
                    </option>
                  ))}
                </select>
              </>
            )}
          </aside>

          <div className="flex min-w-0 flex-1 flex-col">
            <div className="shrink-0 border-b border-neutral-100 p-3">
              <input
                type="search"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Search code, title, instructor…"
                className="w-full rounded border border-neutral-300 px-3 py-2 text-sm outline-none focus:border-[var(--scu-red)] focus:ring-1 focus:ring-[var(--scu-red)]"
              />
            </div>
            <div className="min-h-0 flex-1 overflow-auto">
              {loading && <p className="p-4 text-sm text-neutral-400">Loading…</p>}
              {error && <p className="p-4 text-sm text-red-600">{error}</p>}
              {!loading && !error && sections.length === 0 && (
                <p className="p-4 text-sm text-neutral-400">No matching sections. Try clearing filters.</p>
              )}
              {!loading && !error && sections.length > 0 && (
                <table className="w-full text-left text-xs">
                  <thead className="sticky top-0 bg-neutral-50 text-neutral-600">
                    <tr>
                      <th className="px-2 py-2 font-semibold">Section</th>
                      <th className="px-2 py-2 font-semibold">Units</th>
                      <th className="px-2 py-2 font-semibold">Meeting</th>
                      <th className="px-2 py-2 font-semibold">Tags</th>
                      <th className="px-2 py-2" />
                    </tr>
                  </thead>
                  <tbody>
                    {sections.map((sec) => {
                      const added = existing.has(sec.course.toUpperCase());
                      return (
                        <tr key={`${sec.course}-${sec.section}`} className="border-t border-neutral-50">
                          <td className="px-2 py-2">
                            <span className="font-semibold">{sec.course}</span>
                            <span className="text-neutral-400"> -{sec.section}</span>
                            {sec.title && (
                              <p className="truncate text-[10px] text-neutral-500">{sec.title}</p>
                            )}
                          </td>
                          <td className="px-2 py-2">{sec.units ?? "—"}</td>
                          <td className="px-2 py-2 max-w-[140px] truncate">
                            {sec.meeting_pattern ?? "TBD"}
                          </td>
                          <td className="px-2 py-2 max-w-[120px] truncate text-[10px] text-neutral-500">
                            {(sec.course_tags ?? []).slice(0, 2).join(", ")}
                          </td>
                          <td className="px-2 py-2 text-right">
                            <button
                              type="button"
                              disabled={added}
                              onClick={() => handleAdd(sec)}
                              className="rounded bg-[var(--scu-red)] px-2 py-1 text-[10px] font-semibold text-white disabled:opacity-40"
                            >
                              {added ? "Added" : "Add"}
                            </button>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              )}
            </div>
            <footer className="shrink-0 border-t border-neutral-100 px-3 py-2 text-[10px] text-neutral-500">
              Showing {sections.length} of {total} sections
            </footer>
          </div>
        </div>
      </div>
    </div>
  );
}
