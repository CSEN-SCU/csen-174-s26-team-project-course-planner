import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import {
  searchCatalogSections,
  type CatalogMeetingTimeSlot,
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

/** Matches backend ``catalog_time_windows()`` (2-hour blocks, 8 AM–10 PM). */
const DEFAULT_TIME_WINDOWS: CatalogMeetingTimeSlot[] = [
  { id: "0:120", label: "8:00 AM – 10:00 AM", window_start_min: 0, window_end_min: 120 },
  { id: "120:240", label: "10:00 AM – 12:00 PM", window_start_min: 120, window_end_min: 240 },
  { id: "240:360", label: "12:00 PM – 2:00 PM", window_start_min: 240, window_end_min: 360 },
  { id: "360:480", label: "2:00 PM – 4:00 PM", window_start_min: 360, window_end_min: 480 },
  { id: "480:600", label: "4:00 PM – 6:00 PM", window_start_min: 480, window_end_min: 600 },
  { id: "600:720", label: "6:00 PM – 8:00 PM", window_start_min: 600, window_end_min: 720 },
  { id: "720:840", label: "8:00 PM – 10:00 PM", window_start_min: 720, window_end_min: 840 },
];

const DAY_OPTIONS = [0, 1, 2, 3, 4] as const;

function FilterSection({
  title,
  open,
  onToggle,
  children,
}: {
  title: string;
  open: boolean;
  onToggle: () => void;
  children: ReactNode;
}) {
  return (
    <div className="border-b border-neutral-200 pb-2 mb-2 last:border-0">
      <button
        type="button"
        onClick={onToggle}
        className="flex w-full items-center justify-between gap-2 py-1 text-left font-semibold text-neutral-700 hover:text-[var(--scu-text)]"
        aria-expanded={open}
      >
        <span>{title}</span>
        <span className="text-[10px] text-neutral-400" aria-hidden>
          {open ? "▾" : "▸"}
        </span>
      </button>
      {open && <div className="mt-1.5">{children}</div>}
    </div>
  );
}

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
  const [meetingTimes, setMeetingTimes] = useState<string[]>([]);
  const [tags, setTags] = useState<string[]>([]);
  const [sections, setSections] = useState<CatalogSection[]>([]);
  const [total, setTotal] = useState(0);
  const [facets, setFacets] = useState<{
    subjects: string[];
    tags: { Core: string[]; Other: string[] };
    meeting_times: CatalogMeetingTimeSlot[];
  } | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [slotFilterActive, setSlotFilterActive] = useState(false);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [openDays, setOpenDays] = useState(true);
  const [openMeetingTimes, setOpenMeetingTimes] = useState(true);
  const [openTags, setOpenTags] = useState(true);
  const [openSubjects, setOpenSubjects] = useState(true);
  const wasOpenRef = useRef(false);

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
        meeting_time: meetingTimes.length ? meetingTimes : undefined,
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
  }, [open, query, subjects, days, meetingTimes, tags, slotParams]);

  useEffect(() => {
    if (!open) return;
    const t = window.setTimeout(() => void fetchSections(), 300);
    return () => window.clearTimeout(t);
  }, [open, fetchSections]);

  useEffect(() => {
    if (open && !wasOpenRef.current) {
      setQuery("");
      setSubjects([]);
      setDays([]);
      setMeetingTimes([]);
      setTags([]);
      setExpandedId(null);
      setSlotFilterActive(context.mode === "slot");
      setOpenDays(true);
      setOpenMeetingTimes(true);
      setOpenTags(true);
      setOpenSubjects(true);
    }
    wasOpenRef.current = open;
  }, [open, context.mode]);

  if (!open) return null;

  const toggleInList = <T,>(list: T[], item: T, set: (v: T[]) => void) => {
    set(list.includes(item) ? list.filter((x) => x !== item) : [...list, item]);
  };

  const clearSidebarFilters = () => {
    setQuery("");
    setSubjects([]);
    setDays([]);
    setMeetingTimes([]);
    setTags([]);
  };

  const toggleMeetingTime = (slotId: string) => {
    setSlotFilterActive(false);
    toggleInList(meetingTimes, slotId, setMeetingTimes);
  };

  const hasSidebarFilters =
    query.trim() !== "" ||
    subjects.length > 0 ||
    days.length > 0 ||
    meetingTimes.length > 0 ||
    tags.length > 0;

  const meetingTimeOptions =
    facets?.meeting_times?.length ? facets.meeting_times : DEFAULT_TIME_WINDOWS;

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
      <div className="flex h-[min(92vh,820px)] w-full max-w-6xl flex-col overflow-hidden rounded-lg bg-white shadow-xl ring-1 ring-neutral-200">
        <header className="flex shrink-0 items-start justify-between gap-3 border-b border-neutral-200 px-5 py-3">
          <div>
            <h2 id="course-browser-title" className="text-lg font-semibold text-[var(--scu-text)]">
              Browse courses
            </h2>
            {context.mode === "slot" && slotFilterActive && (
              <p className="mt-1 text-sm text-[var(--scu-red)]">
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
            className="rounded px-2 py-1 text-lg text-neutral-500 hover:bg-neutral-100"
            aria-label="Close"
          >
            ✕
          </button>
        </header>

        <div className="flex min-h-0 flex-1">
          <aside className="w-60 shrink-0 overflow-y-auto border-r border-neutral-100 bg-neutral-50 p-3 text-sm">
            <div className="mb-3 flex items-center justify-between gap-2">
              <p className="font-semibold text-neutral-800">Filters</p>
              <button
                type="button"
                onClick={clearSidebarFilters}
                disabled={!hasSidebarFilters}
                className="shrink-0 rounded border border-neutral-300 bg-white px-2 py-1 text-xs font-semibold text-neutral-600 transition hover:bg-neutral-100 disabled:cursor-default disabled:opacity-40"
              >
                Clear filters
              </button>
            </div>

            <FilterSection
              title="Days offered"
              open={openDays}
              onToggle={() => setOpenDays((o) => !o)}
            >
              <div className="flex flex-wrap gap-1">
                {DAY_OPTIONS.map((d) => (
                  <button
                    key={d}
                    type="button"
                    onClick={() => toggleInList(days, d, setDays)}
                    className={`rounded-md px-2.5 py-1 text-xs transition ${
                      days.includes(d)
                        ? "bg-[var(--scu-red)] font-medium text-white shadow-sm"
                        : "bg-white text-neutral-700 ring-1 ring-neutral-200 hover:bg-neutral-50"
                    }`}
                    aria-pressed={days.includes(d)}
                  >
                    {WEEKDAY_LABELS[d]}
                  </button>
                ))}
              </div>
            </FilterSection>

            <FilterSection
              title="Time of day"
              open={openMeetingTimes}
              onToggle={() => setOpenMeetingTimes((o) => !o)}
            >
              <p className="mb-1.5 text-[10px] leading-snug text-neutral-500">
                Includes sections that meet at least 30 minutes in the window (long labs span
                multiple blocks).
              </p>
              <div className="space-y-1">
                {meetingTimeOptions.map((slot) => {
                  const active = meetingTimes.includes(slot.id);
                  return (
                    <button
                      key={slot.id}
                      type="button"
                      onClick={() => toggleMeetingTime(slot.id)}
                      className={`flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-xs transition ${
                        active
                          ? "bg-[var(--scu-red)] font-medium text-white shadow-sm"
                          : "bg-white text-neutral-700 ring-1 ring-neutral-200 hover:bg-neutral-50"
                      }`}
                      aria-pressed={active}
                    >
                      <span
                        className={`flex h-3.5 w-3.5 shrink-0 items-center justify-center rounded border text-[9px] ${
                          active ? "border-white/60 bg-white/20" : "border-neutral-300 bg-white"
                        }`}
                        aria-hidden
                      >
                        {active ? "✓" : ""}
                      </span>
                      <span>{slot.label}</span>
                    </button>
                  );
                })}
              </div>
            </FilterSection>

            {facets?.tags?.Core && facets.tags.Core.length > 0 && (
              <FilterSection
                title="Core requirements"
                open={openTags}
                onToggle={() => setOpenTags((o) => !o)}
              >
                <div className="max-h-40 overflow-y-auto space-y-1">
                  {facets.tags.Core.map((t) => (
                    <label key={t} className="flex items-center gap-2">
                      <input
                        type="checkbox"
                        checked={tags.includes(t)}
                        onChange={() => toggleInList(tags, t, setTags)}
                      />
                      <span className="text-xs">{t}</span>
                    </label>
                  ))}
                </div>
              </FilterSection>
            )}

            {facets?.subjects && facets.subjects.length > 0 && (
              <FilterSection
                title="Course subject"
                open={openSubjects}
                onToggle={() => setOpenSubjects((o) => !o)}
              >
                <div className="max-h-44 overflow-y-auto pr-1">
                  <div className="space-y-1">
                    {facets.subjects.map((s) => {
                      const active = subjects.includes(s);
                      return (
                        <button
                          key={s}
                          type="button"
                          onClick={() => toggleInList(subjects, s, setSubjects)}
                          className={`flex w-full items-start gap-2 rounded-md px-2 py-1.5 text-left text-xs transition ${
                            active
                              ? "bg-[var(--scu-red)] font-medium text-white shadow-sm"
                              : "bg-white text-neutral-700 ring-1 ring-neutral-200 hover:bg-neutral-50"
                          }`}
                          aria-pressed={active}
                        >
                          <span
                            className={`mt-0.5 flex h-3.5 w-3.5 shrink-0 items-center justify-center rounded border text-[9px] ${
                              active ? "border-white/60 bg-white/20" : "border-neutral-300 bg-white"
                            }`}
                            aria-hidden
                          >
                            {active ? "✓" : ""}
                          </span>
                          <span className="min-w-0 flex-1 break-words leading-snug">{s}</span>
                        </button>
                      );
                    })}
                  </div>
                </div>
              </FilterSection>
            )}
          </aside>

          <div className="flex min-w-0 flex-1 flex-col">
            <div className="shrink-0 border-b border-neutral-100 p-3">
              <input
                type="search"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Search code, title, instructor…"
                className="w-full rounded border border-neutral-300 px-3 py-2.5 text-sm outline-none focus:border-[var(--scu-red)] focus:ring-1 focus:ring-[var(--scu-red)]"
              />
            </div>
            <div className="min-h-0 flex-1 overflow-auto">
              {loading && <p className="p-4 text-sm text-neutral-400">Loading…</p>}
              {error && <p className="p-4 text-sm text-red-600">{error}</p>}
              {!loading && !error && sections.length === 0 && (
                <p className="p-4 text-sm text-neutral-400">No matching sections. Try clearing filters.</p>
              )}
              {!loading && !error && sections.length > 0 && (
                <ul className="divide-y divide-neutral-100">
                  {sections.map((sec) => {
                    const rowId = `${sec.course}-${sec.section}`;
                    const added = existing.has(sec.course.toUpperCase());
                    const expanded = expandedId === rowId;
                    return (
                      <li key={rowId} className="bg-white">
                        <div className="flex items-start gap-2 px-4 py-3">
                          <button
                            type="button"
                            onClick={() => setExpandedId(expanded ? null : rowId)}
                            className="mt-0.5 shrink-0 rounded p-1 text-neutral-400 hover:bg-neutral-100"
                            aria-expanded={expanded}
                            aria-label={expanded ? "Collapse details" : "Expand details"}
                          >
                            {expanded ? "▾" : "▸"}
                          </button>
                          <div className="min-w-0 flex-1">
                            <div className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5">
                              <span className="text-sm font-semibold text-[var(--scu-text)]">
                                {sec.course}
                                <span className="font-normal text-neutral-500"> -{sec.section}</span>
                              </span>
                              {sec.status && (
                                <span className="rounded bg-neutral-100 px-1.5 py-0.5 text-[10px] text-neutral-600">
                                  {sec.status}
                                </span>
                              )}
                              {sec.units != null && (
                                <span className="text-xs text-neutral-500">{sec.units} units</span>
                              )}
                            </div>
                            {sec.title && (
                              <p className="mt-0.5 text-sm text-neutral-600">{sec.title}</p>
                            )}
                            {!expanded && sec.meeting_pattern && (
                              <p className="mt-1 truncate text-xs text-neutral-500">
                                {sec.meeting_pattern}
                              </p>
                            )}
                          </div>
                          <button
                            type="button"
                            disabled={added}
                            onClick={() => handleAdd(sec)}
                            className="shrink-0 rounded bg-[var(--scu-red)] px-3 py-1.5 text-xs font-semibold text-white disabled:opacity-40"
                          >
                            {added ? "Added" : "Add"}
                          </button>
                        </div>
                        {expanded && (
                          <div className="border-t border-neutral-50 bg-neutral-50/80 px-4 py-3 pl-11 text-sm text-neutral-700">
                            <dl className="grid gap-2 sm:grid-cols-2">
                              <div>
                                <dt className="text-xs font-semibold uppercase text-neutral-500">
                                  Meeting
                                </dt>
                                <dd className="mt-0.5 whitespace-pre-wrap">
                                  {sec.meeting_pattern ?? "Not posted"}
                                </dd>
                              </div>
                              <div>
                                <dt className="text-xs font-semibold uppercase text-neutral-500">
                                  Location
                                </dt>
                                <dd className="mt-0.5">{sec.location ?? "—"}</dd>
                              </div>
                              <div>
                                <dt className="text-xs font-semibold uppercase text-neutral-500">
                                  Instructors
                                </dt>
                                <dd className="mt-0.5">
                                  {(sec.instructors ?? []).join(", ") || "TBA"}
                                </dd>
                              </div>
                              <div>
                                <dt className="text-xs font-semibold uppercase text-neutral-500">
                                  Enrollment
                                </dt>
                                <dd className="mt-0.5">{sec.enrolled_capacity ?? "—"}</dd>
                              </div>
                              <div className="sm:col-span-2">
                                <dt className="text-xs font-semibold uppercase text-neutral-500">
                                  Requirement tags
                                </dt>
                                <dd className="mt-0.5">
                                  {(sec.course_tags ?? []).length > 0
                                    ? (sec.course_tags ?? []).join(" · ")
                                    : "—"}
                                </dd>
                              </div>
                            </dl>
                          </div>
                        )}
                      </li>
                    );
                  })}
                </ul>
              )}
            </div>
            <footer className="shrink-0 border-t border-neutral-100 px-4 py-2 text-xs text-neutral-500">
              Showing {sections.length} of {total} sections
            </footer>
          </div>
        </div>
      </div>
    </div>
  );
}
