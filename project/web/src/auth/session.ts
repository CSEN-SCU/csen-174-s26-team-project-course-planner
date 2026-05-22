const USER_ID_KEY = "scu_planner_user_id";
const GOOGLE_OAUTH_PENDING_KEY = "scu_planner_google_oauth_pending";

export function readStoredUserId(): string | null {
  if (typeof window === "undefined") return null;
  const id = sessionStorage.getItem(USER_ID_KEY);
  return id && id.length > 0 ? id : null;
}

export function persistUserId(userId: string | null): void {
  if (typeof window === "undefined") return;
  if (userId) sessionStorage.setItem(USER_ID_KEY, userId);
  else sessionStorage.removeItem(USER_ID_KEY);
}

/** Clear browser session (sign out). Does not touch server data by itself. */
export function clearLocalSession(): void {
  if (typeof window === "undefined") return;
  sessionStorage.removeItem(USER_ID_KEY);
  sessionStorage.removeItem(GOOGLE_OAUTH_PENDING_KEY);
}

/** Handoff token present while returning from Google OAuth (before exchange). */
export function readGoogleOauthHandoffFromUrl(): string | null {
  if (typeof window === "undefined") return null;
  const token = new URLSearchParams(window.location.search).get("google_oauth");
  return token && token.length > 0 ? token : null;
}

/** True when finishing Google sign-in (survives URL cleanup / Strict Mode remount). */
export function isGoogleOauthPending(): boolean {
  if (typeof window === "undefined") return false;
  if (readGoogleOauthHandoffFromUrl()) {
    sessionStorage.setItem(GOOGLE_OAUTH_PENDING_KEY, "1");
    return true;
  }
  return sessionStorage.getItem(GOOGLE_OAUTH_PENDING_KEY) === "1";
}

export function clearGoogleOauthPending(): void {
  if (typeof window === "undefined") return;
  sessionStorage.removeItem(GOOGLE_OAUTH_PENDING_KEY);
}
