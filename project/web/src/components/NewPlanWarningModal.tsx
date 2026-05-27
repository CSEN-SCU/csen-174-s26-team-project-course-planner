export type NewPlanWarningModalProps = {
  open: boolean;
  onSaveFirst: () => void;
  onStartWithoutSaving: () => void;
  onCancel: () => void;
};

export function NewPlanWarningModal({
  open,
  onSaveFirst,
  onStartWithoutSaving,
  onCancel,
}: NewPlanWarningModalProps) {
  if (!open) return null;

  return (
    <div className="fixed inset-0 z-[70] flex items-center justify-center bg-black/40 p-4">
      <section
        role="alertdialog"
        aria-modal="true"
        aria-labelledby="new-plan-warning-title"
        aria-describedby="new-plan-warning-desc"
        className="w-full max-w-md rounded-lg bg-white p-6 shadow-xl ring-1 ring-neutral-200"
      >
        <h2 id="new-plan-warning-title" className="text-lg font-semibold text-[var(--scu-text)]">
          Save your schedule first?
        </h2>
        <p id="new-plan-warning-desc" className="mt-2 text-sm text-neutral-600">
          You have courses on your calendar that are not saved yet. Save this schedule before
          starting a new plan, or continue without saving.
        </p>
        <div className="mt-5 flex flex-col gap-2">
          <button
            type="button"
            onClick={onSaveFirst}
            className="rounded-md bg-[var(--scu-red)] px-4 py-2.5 text-sm font-semibold text-white hover:bg-[var(--scu-dark-red)]"
          >
            Save schedule first
          </button>
          <button
            type="button"
            onClick={onStartWithoutSaving}
            className="rounded-md border border-neutral-300 px-4 py-2.5 text-sm font-semibold text-neutral-800 hover:bg-neutral-50"
          >
            Start new plan without saving
          </button>
          <button
            type="button"
            onClick={onCancel}
            className="text-xs text-neutral-500 hover:text-neutral-800"
          >
            Cancel
          </button>
        </div>
      </section>
    </div>
  );
}
