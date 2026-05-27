import { useLayoutEffect, useRef } from "react";
import { resetPageScroll } from "../lib/scroll";
import { BrandLink } from "./BrandLink";

export type MemorySessionRow = {
  id: string;
  title: string;
  dateLabel: string;
  kind: "memory" | "snapshot" | "current";
  memoryContent?: string;
  recommended?: Record<string, unknown>[];
  messages?: { id: string; role: string; content: string }[];
};

export type LeftPanelProps = {
  sessions: MemorySessionRow[];
  activeSessionId: string | null;
  scheduleCourseCount: number;
  onSelectSession: (row: MemorySessionRow) => void;
  onDeleteSession?: (id: string) => void;
  onNewPlan: () => void;
  onSaveSchedule: () => void;
  onClearSchedule: () => void;
};

export function LeftPanel({
  sessions,
  activeSessionId,
  scheduleCourseCount,
  onSelectSession,
  onDeleteSession,
  onNewPlan,
  onSaveSchedule,
  onClearSchedule,
}: LeftPanelProps) {
  const asideRef = useRef<HTMLElement>(null);
  const sessionsRef = useRef<HTMLDivElement>(null);

  useLayoutEffect(() => {
    resetPageScroll();
    if (asideRef.current) asideRef.current.scrollTop = 0;
    if (sessionsRef.current) sessionsRef.current.scrollTop = 0;
  }, []);

  return (
    <aside
      ref={asideRef}
      className="grid h-full min-h-0 w-[260px] shrink-0 grid-rows-[auto_auto_minmax(0,1fr)] overflow-hidden border-l-4 border-[var(--scu-red)] bg-[var(--scu-white)] shadow-sm"
    >
      <header className="z-10 border-b border-neutral-200 bg-[var(--scu-white)] px-4 py-5">
        <BrandLink />
      </header>

      <div className="space-y-2 bg-[var(--scu-white)] px-4 py-4">
        {scheduleCourseCount > 0 ? (
          <>
            <button
              type="button"
              onClick={onSaveSchedule}
              disabled={scheduleCourseCount === 0}
              className="w-full rounded-md bg-[var(--scu-red)] px-3 py-2.5 text-sm font-semibold text-white shadow-sm transition hover:bg-[var(--scu-dark-red)] disabled:cursor-not-allowed disabled:opacity-50"
            >
              Save schedule
            </button>
            <button
              type="button"
              onClick={onClearSchedule}
              disabled={scheduleCourseCount === 0}
              className="w-full rounded-md border border-neutral-300 bg-white px-3 py-2.5 text-sm font-semibold text-neutral-700 transition hover:bg-neutral-50 disabled:cursor-not-allowed disabled:opacity-40"
            >
              Clear schedule
            </button>
            <div className="border-t border-neutral-200 pt-2">
              <button
                type="button"
                onClick={onNewPlan}
                className="w-full rounded-md border border-neutral-300 bg-neutral-50 px-3 py-2 text-sm font-semibold text-neutral-700 transition hover:bg-neutral-100"
              >
                New plan
              </button>
            </div>
          </>
        ) : (
          <button
            type="button"
            onClick={onNewPlan}
            className="w-full rounded-md bg-[var(--scu-red)] px-3 py-2.5 text-sm font-semibold text-white shadow-sm transition hover:bg-[var(--scu-dark-red)]"
          >
            New Plan
          </button>
        )}
      </div>

      <div ref={sessionsRef} className="min-h-0 overflow-y-auto px-2 pb-4">
        <p className="px-2 pb-2 text-xs font-semibold uppercase tracking-wide text-neutral-400">
          Past sessions
        </p>
        <ul className="space-y-1">
          {sessions.length === 0 && (
            <li className="px-2 py-2 text-xs text-neutral-400">No saved schedules yet.</li>
          )}
          {sessions.map((s) => {
            const active = s.id === activeSessionId;
            return (
              <li key={s.id} className="group relative">
                <button
                  type="button"
                  onClick={() => onSelectSession(s)}
                  className={`w-full rounded-md px-3 py-2.5 pr-8 text-left text-sm transition ${
                    active
                      ? "bg-[var(--scu-gray)] font-medium text-[var(--scu-text)] ring-1 ring-neutral-200"
                      : "text-neutral-700 hover:bg-neutral-50"
                  }`}
                >
                  <span className="block truncate">{s.title}</span>
                  <span className="mt-0.5 block text-xs text-neutral-500">
                    {s.dateLabel}
                  </span>
                </button>
                {onDeleteSession && s.kind !== "current" && (
                  <button
                    type="button"
                    onClick={(e) => {
                      e.stopPropagation();
                      onDeleteSession(s.id);
                    }}
                    className="absolute right-1.5 top-1/2 -translate-y-1/2 rounded p-1 text-neutral-300 opacity-0 transition group-hover:opacity-100 hover:bg-red-50 hover:text-red-500"
                    aria-label={`Delete ${s.title}`}
                  >
                    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" aria-hidden>
                      <path
                        d="M18 6L6 18M6 6l12 12"
                        stroke="currentColor"
                        strokeWidth="2.5"
                        strokeLinecap="round"
                      />
                    </svg>
                  </button>
                )}
              </li>
            );
          })}
        </ul>
      </div>
    </aside>
  );
}
