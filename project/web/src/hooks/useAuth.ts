import { useCallback, useLayoutEffect, useState } from "react";
import { exchangeGoogleOauth } from "../api/client";
import {
  clearGoogleOauthPending,
  isGoogleOauthPending,
  persistUserId,
  readStoredUserId,
} from "../auth/session";

export function useAuth() {
  const [userId, setUserIdState] = useState<string | null>(() => readStoredUserId());
  const [googleAuthError, setGoogleAuthError] = useState<string | null>(null);
  const [googleAuthPending, setGoogleAuthPending] = useState(() => isGoogleOauthPending());

  const setUserId = useCallback((id: string | null) => {
    persistUserId(id);
    setUserIdState(id);
  }, []);

  const signOut = useCallback(() => {
    setUserId(null);
    setGoogleAuthError(null);
  }, [setUserId]);

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
          setUserId(String(r.user_id));
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
    signOut,
  };
}
