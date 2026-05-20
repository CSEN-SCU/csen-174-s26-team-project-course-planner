type DeleteUserDataConfirmProps = {
  open: boolean;
  busy?: boolean;
  error?: string | null;
  onConfirm: () => void;
  onCancel: () => void;
};

export function DeleteUserDataConfirm({
  open,
  busy = false,
  error,
  onConfirm,
  onCancel,
}: DeleteUserDataConfirmProps) {
  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-[200] flex items-center justify-center bg-black/40 px-4"
      role="presentation"
      onClick={onCancel}
    >
      <div
        role="alertdialog"
        aria-modal="true"
        aria-labelledby="delete-user-data-title"
        aria-describedby="delete-user-data-desc"
        className="w-full max-w-md rounded-lg border border-neutral-200 bg-white p-6 shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <h2
          id="delete-user-data-title"
          className="text-center text-base font-semibold text-[var(--scu-text)] sm:text-lg"
        >
          Delete all user data from SCU Course Planner?
        </h2>
        <p id="delete-user-data-desc" className="sr-only">
          This permanently removes your account, saved plans, transcript data, and preferences.
        </p>
        {error && (
          <p className="mt-3 rounded border border-red-200 bg-red-50 px-3 py-2 text-center text-xs text-red-700">
            {error}
          </p>
        )}
        <div className="mt-6 flex flex-col-reverse gap-2 sm:flex-row sm:justify-center sm:gap-3">
          <button
            type="button"
            onClick={onCancel}
            disabled={busy}
            className="rounded-md border border-neutral-300 bg-neutral-100 px-5 py-2.5 text-sm font-semibold text-neutral-700 transition hover:bg-neutral-200 disabled:opacity-60"
          >
            No
          </button>
          <button
            type="button"
            onClick={onConfirm}
            disabled={busy}
            className="rounded-md bg-[var(--scu-red)] px-5 py-2.5 text-sm font-semibold text-white shadow-sm ring-2 ring-[var(--scu-red)] ring-offset-2 transition hover:bg-[var(--scu-dark-red)] disabled:opacity-60"
          >
            {busy ? "Deleting…" : "Yes"}
          </button>
        </div>
      </div>
    </div>
  );
}
