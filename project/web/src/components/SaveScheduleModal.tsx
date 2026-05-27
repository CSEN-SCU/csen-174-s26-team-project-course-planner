import { useEffect, useState } from "react";

export type SaveScheduleModalProps = {
  open: boolean;
  defaultName?: string;
  courseCount: number;
  onSave: (name: string) => void;
  onClose: () => void;
};

export function SaveScheduleModal({
  open,
  defaultName = "",
  courseCount,
  onSave,
  onClose,
}: SaveScheduleModalProps) {
  const [name, setName] = useState(defaultName);

  useEffect(() => {
    if (open) setName(defaultName);
  }, [open, defaultName]);

  if (!open) return null;

  const trimmed = name.trim();
  const canSave = trimmed.length > 0 && courseCount > 0;

  return (
    <div className="fixed inset-0 z-[70] flex items-center justify-center bg-black/40 p-4">
      <section
        role="dialog"
        aria-modal="true"
        aria-labelledby="save-schedule-title"
        className="w-full max-w-md rounded-lg bg-white p-6 shadow-xl ring-1 ring-neutral-200"
      >
        <h2 id="save-schedule-title" className="text-lg font-semibold text-[var(--scu-text)]">
          Save schedule
        </h2>
        <p className="mt-2 text-sm text-neutral-600">
          Give this schedule a name so you can find it under Past sessions.
        </p>
        <label className="mt-4 block">
          <span className="text-xs font-semibold uppercase tracking-wide text-neutral-500">
            Schedule name
          </span>
          <input
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="e.g. Fall 2026 — light load"
            className="mt-1 w-full rounded-md border border-neutral-300 px-3 py-2 text-sm outline-none focus:border-[var(--scu-red)] focus:ring-1 focus:ring-[var(--scu-red)]"
            autoFocus
          />
        </label>
        {courseCount === 0 && (
          <p className="mt-2 text-xs text-amber-700">Add at least one course before saving.</p>
        )}
        <div className="mt-5 flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
          <button
            type="button"
            onClick={onClose}
            className="rounded-md border border-neutral-300 px-4 py-2 text-sm font-semibold text-neutral-700 hover:bg-neutral-50"
          >
            Cancel
          </button>
          <button
            type="button"
            disabled={!canSave}
            onClick={() => onSave(trimmed)}
            className="rounded-md bg-[var(--scu-red)] px-4 py-2 text-sm font-semibold text-white hover:bg-[var(--scu-dark-red)] disabled:cursor-not-allowed disabled:opacity-50"
          >
            Save
          </button>
        </div>
      </section>
    </div>
  );
}
