import { useEffect } from "react";
import { resetPageScroll } from "../lib/scroll";

/** Shown briefly while the local session is cleared after sign out. */
export function SignOutLoadingPage() {
  useEffect(() => {
    resetPageScroll();
  }, []);

  return (
    <div
      className="planner-app-root flex flex-col items-center justify-center gap-3"
      role="status"
      aria-live="polite"
      aria-busy="true"
    >
      <div
        className="h-8 w-8 animate-spin rounded-full border-4 border-[var(--scu-red)] border-t-transparent"
        aria-hidden
      />
      <p className="text-sm text-neutral-500">Signing out…</p>
    </div>
  );
}
