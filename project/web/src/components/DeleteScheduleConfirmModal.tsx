export type DeleteScheduleConfirmModalProps = {
  open: boolean;
  scheduleTitle: string;
  onConfirm: () => void;
  onCancel: () => void;
};

export function DeleteScheduleConfirmModal({
  open,
  scheduleTitle,
  onConfirm,
  onCancel,
}: DeleteScheduleConfirmModalProps) {
  if (!open) return null;

  const label = scheduleTitle.trim() || "this schedule";

  return (
    <div
      className="fixed inset-0 z-[70] flex items-center justify-center bg-black/40 p-4"
      role="presentation"
      onClick={onCancel}
    >
      <section
        role="alertdialog"
        aria-modal="true"
        aria-labelledby="delete-schedule-title"
        aria-describedby="delete-schedule-desc"
        className="w-full max-w-md rounded-lg bg-white p-6 shadow-xl ring-1 ring-neutral-200"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 id="delete-schedule-title" className="text-lg font-semibold text-[var(--scu-text)]">
          Delete this schedule?
        </h2>
        <p id="delete-schedule-desc" className="mt-2 text-sm text-neutral-600">
          Are you sure you want to delete <span className="font-medium text-neutral-800">{label}</span>
          ? This removes it from your saved schedules and cannot be undone.
        </p>
        <div className="mt-5 flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
          <button
            type="button"
            onClick={onCancel}
            className="rounded-md border border-neutral-300 px-4 py-2.5 text-sm font-semibold text-neutral-700 hover:bg-neutral-50"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={onConfirm}
            className="rounded-md bg-[var(--scu-red)] px-4 py-2.5 text-sm font-semibold text-white hover:bg-[var(--scu-dark-red)]"
          >
            Delete schedule
          </button>
        </div>
      </section>
    </div>
  );
}
