const USER_ID_KEY = "scu_planner_user_id_v2";
const SESSION_TOKEN_KEY = "scu_planner_session_token";
const LEGACY_USER_ID_KEY = "scu_planner_user_id";
const GOOGLE_OAUTH_PENDING_KEY = "scu_planner_google_oauth_pending";

export function readStoredUserId(): string | null {
  if (typeof window === "undefined") return null;
  // Drop legacy small integer ids (1, 2, 3) that caused cross-user memory leaks.
  const legacy = sessionStorage.getItem(LEGACY_USER_ID_KEY);
  if (legacy) {
    sessionStorage.removeItem(LEGACY_USER_ID_KEY);
    sessionStorage.removeItem(SESSION_TOKEN_KEY);
  }
  const id = sessionStorage.getItem(USER_ID_KEY);
  if (!id || id.length === 0) return null;
  // Require a session token so API calls cannot use a stale/guessed user id alone.
  if (!readSessionToken()) {
    sessionStorage.removeItem(USER_ID_KEY);
    return null;
  }
  return id;
}

export function readSessionToken(): string | null {
  if (typeof window === "undefined") return null;
  const token = sessionStorage.getItem(SESSION_TOKEN_KEY);
  return token && token.length > 0 ? token : null;
}

export function persistUserId(userId: string | null): void {
  if (typeof window === "undefined") return;
  if (userId) sessionStorage.setItem(USER_ID_KEY, userId);
  else sessionStorage.removeItem(USER_ID_KEY);
}

export function persistSessionToken(token: string | null): void {
  if (typeof window === "undefined") return;
  if (token) sessionStorage.setItem(SESSION_TOKEN_KEY, token);
  else sessionStorage.removeItem(SESSION_TOKEN_KEY);
}

// Prefix of the per-user "first-login onboarding carousel seen" flag in
// localStorage (see App.tsx). Cleared on sign-out so the carousel reliably
// reappears on the next sign-in for any user who has no saved data.
const INTRO_SEEN_KEY_PREFIX = "scu_planner_intro_seen";

/** Clear browser session (sign out). Does not touch server data by itself. */
export function clearLocalSession(): void {
  if (typeof window === "undefined") return;
  sessionStorage.removeItem(USER_ID_KEY);
  sessionStorage.removeItem(LEGACY_USER_ID_KEY);
  sessionStorage.removeItem(SESSION_TOKEN_KEY);
  sessionStorage.removeItem(GOOGLE_OAUTH_PENDING_KEY);
  try {
    for (let i = localStorage.length - 1; i >= 0; i--) {
      const key = localStorage.key(i);
      if (key && key.startsWith(INTRO_SEEN_KEY_PREFIX)) {
        localStorage.removeItem(key);
      }
    }
  } catch {
    /* ignore */
  }
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
