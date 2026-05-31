import { useEffect } from "react";
import { resetPageScroll } from "../lib/scroll";

/** Shown while Google OAuth handoff completes — avoids flashing the sign-in landing page. */
export function AuthLoadingPage() {
  useEffect(() => {
    resetPageScroll();
  }, []);

  return (
    <div
      className="planner-app-root flex items-center justify-center"
      role="status"
      aria-live="polite"
      aria-busy="true"
    >
      <p className="text-sm text-neutral-500">Signing in with Google…</p>
    </div>
  );
}
