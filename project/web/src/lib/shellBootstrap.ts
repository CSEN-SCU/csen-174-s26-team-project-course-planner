import { resetPageScroll } from "./scroll";

const USER_ID_KEY = "scu_planner_user_id_v2";
const SESSION_TOKEN_KEY = "scu_planner_session_token";
const HTML_CLASS = "planner-shell";

/** Apply scroll lock before React paints when a session is already stored. */
export function bootstrapPlannerShellClass(): void {
  if (typeof window === "undefined") return;
  if ("scrollRestoration" in window.history) {
    window.history.scrollRestoration = "manual";
  }
  resetPageScroll();
  try {
    const uid = sessionStorage.getItem(USER_ID_KEY);
    const tok = sessionStorage.getItem(SESSION_TOKEN_KEY);
    if (uid && tok) {
      document.documentElement.classList.add(HTML_CLASS);
      resetPageScroll();
    }
  } catch {
    /* sessionStorage unavailable */
  }
}
