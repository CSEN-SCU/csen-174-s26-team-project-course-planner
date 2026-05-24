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
          Delete user data?
        </h2>
        <p
          id="delete-user-data-desc"
          className="mt-3 text-center text-sm leading-relaxed text-neutral-600"
        >
          This permanently removes all data associated with your account from our servers —
          including saved schedules, your Academic Progress upload, course preferences, and chat
          history — and signs you out on this device. This action cannot be undone.
        </p>
        {error && (
          <p className="mt-3 rounded border border-amber-200 bg-amber-50 px-3 py-2 text-center text-xs text-amber-900">
            {error}
          </p>
        )}
        <div className="mt-6 flex flex-col-reverse gap-2 sm:flex-row sm:justify-center sm:gap-3">
          <button
            type="button"
            onClick={onCancel}
            className="rounded-md border border-neutral-300 bg-neutral-100 px-5 py-2.5 text-sm font-semibold text-neutral-700 transition hover:bg-neutral-200"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={onConfirm}
            disabled={busy}
            className="rounded-md bg-[var(--scu-red)] px-5 py-2.5 text-sm font-semibold text-white shadow-sm transition hover:bg-[var(--scu-dark-red)] disabled:opacity-60"
          >
            {busy ? "Deleting…" : "Delete user data"}
          </button>
        </div>
      </div>
    </div>
  );
}

/** Alias — same flow as delete user data (sign out + server wipe). */
export const SignOutConfirm = DeleteUserDataConfirm;
