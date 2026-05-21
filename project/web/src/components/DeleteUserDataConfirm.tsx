type SignOutConfirmProps = {
  open: boolean;
  busy?: boolean;
  error?: string | null;
  onConfirm: () => void;
  onCancel: () => void;
};

export function SignOutConfirm({
  open,
  busy = false,
  error,
  onConfirm,
  onCancel,
}: SignOutConfirmProps) {
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
        aria-labelledby="sign-out-title"
        aria-describedby="sign-out-desc"
        className="w-full max-w-md rounded-lg border border-neutral-200 bg-white p-6 shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <h2
          id="sign-out-title"
          className="text-center text-base font-semibold text-[var(--scu-text)] sm:text-lg"
        >
          Sign out?
        </h2>
        <p
          id="sign-out-desc"
          className="mt-3 text-center text-sm leading-relaxed text-neutral-600"
        >
          You will return to the home page. Saved plans on this device are cleared. We also try
          to remove your data from the server so you can start fresh when testing.
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
            {busy ? "Signing out…" : "Sign out"}
          </button>
        </div>
      </div>
    </div>
  );
}

/** @deprecated Use SignOutConfirm — kept for existing imports during rename. */
export const DeleteUserDataConfirm = SignOutConfirm;
