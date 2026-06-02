export type PlanStartModalProps = {
  open: boolean;
  onManual: () => void;
  onAi: () => void;
  onClose: () => void;
};

export function PlanStartModal({ open, onManual, onAi, onClose }: PlanStartModalProps) {
  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
      role="presentation"
      onClick={onClose}
    >
      <section
        role="dialog"
        aria-modal="true"
        aria-labelledby="plan-start-title"
        className="w-full max-w-md rounded-lg bg-white p-6 shadow-xl ring-1 ring-neutral-200"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-start justify-between gap-3">
          <h2 id="plan-start-title" className="text-lg font-semibold text-[var(--scu-text)]">
            Start a new plan
          </h2>
          <button
            type="button"
            onClick={onClose}
            className="shrink-0 rounded px-2 py-1 text-lg text-neutral-500 hover:bg-neutral-100"
            aria-label="Close"
          >
            ✕
          </button>
        </div>
        <p className="mt-2 text-sm text-neutral-600">
          How would you like to build your schedule for this quarter?
        </p>
        <div className="mt-5 flex flex-col gap-2">
          <button
            type="button"
            onClick={onManual}
            className="rounded-md bg-[var(--scu-red)] px-4 py-2.5 text-sm font-semibold text-white hover:bg-[var(--scu-dark-red)]"
          >
            Search and add courses myself
          </button>
          <button
            type="button"
            onClick={onAi}
            className="rounded-md border border-neutral-300 px-4 py-2.5 text-sm font-semibold text-[var(--scu-text)] hover:bg-neutral-50"
          >
            Have AI recommend my schedule
          </button>
          <button
            type="button"
            onClick={onClose}
            className="mt-1 text-xs text-neutral-500 hover:text-neutral-800"
          >
            Cancel
          </button>
        </div>
      </section>
    </div>
  );
}
