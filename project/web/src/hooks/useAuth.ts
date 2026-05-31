import { useCallback, useLayoutEffect, useRef, useState } from "react";
import { exchangeGoogleOauth } from "../api/client";
import {
  clearGoogleOauthPending,
  clearLocalSession,
  isGoogleOauthPending,
  persistSessionToken,
  persistUserId,
  readStoredUserId,
} from "../auth/session";

const SIGN_OUT_DELAY_MS = 1000;

export function useAuth() {
  const [userId, setUserIdState] = useState<string | null>(() => readStoredUserId());
  const [googleAuthError, setGoogleAuthError] = useState<string | null>(null);
  const [googleAuthPending, setGoogleAuthPending] = useState(() => isGoogleOauthPending());
  const [signOutPending, setSignOutPending] = useState(false);
  const signOutPendingRef = useRef(false);

  const setUserId = useCallback((id: string | null, sessionToken?: string | null) => {
    persistUserId(id);
    persistSessionToken(sessionToken ?? null);
    setUserIdState(id);
  }, []);

  const signOut = useCallback(() => {
    if (signOutPendingRef.current) return;
    signOutPendingRef.current = true;
    setSignOutPending(true);
    window.setTimeout(() => {
      clearLocalSession();
      setUserIdState(null);
      setGoogleAuthError(null);
      signOutPendingRef.current = false;
      setSignOutPending(false);
    }, SIGN_OUT_DELAY_MS);
  }, []);

  useLayoutEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const token = params.get("google_oauth");
    const err = params.get("google_oauth_error");

    if (!token && !err) return;

    params.delete("google_oauth");
    params.delete("google_oauth_error");
    const q = params.toString();
    window.history.replaceState({}, document.title, q ? `?${q}` : window.location.pathname);

    if (err) {
      clearGoogleOauthPending();
      setGoogleAuthPending(false);
      setGoogleAuthError(
        err === "access_denied" ? "Google sign-in was cancelled." : "Google sign-in failed.",
      );
      return;
    }
    if (!token) {
      clearGoogleOauthPending();
      setGoogleAuthPending(false);
      return;
    }

    setGoogleAuthPending(true);
    void exchangeGoogleOauth(token)
      .then((r) => {
        if (r.success && r.user_id) {
          setUserId(String(r.user_id), r.session_token ?? null);
          setGoogleAuthError(null);
        } else {
          setGoogleAuthError("Google sign-in failed. Please try again.");
        }
      })
      .catch(() => {
        setGoogleAuthError("Google sign-in failed. Please try again.");
      })
      .finally(() => {
        clearGoogleOauthPending();
        setGoogleAuthPending(false);
      });
  }, [setUserId]);

  return {
    userId,
    googleAuthError,
    googleAuthPending,
    signOutPending,
    signOut,
  };
}
