import { useCallback, useLayoutEffect, useState } from "react";
import {
  exchangeGoogleOauth,
  login as apiLogin,
  register as apiRegister,
} from "../api/client";
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

  const handleLogin = useCallback(
    async (username: string, password: string) => {
      try {
        const r = await apiLogin(username, password);
        if (r.success && r.user_id) {
          setUserId(String(r.user_id));
          setGoogleAuthError(null);
          return { ok: true as const };
        }
        return { ok: false as const, error: "Invalid username or password." };
      } catch (e) {
        const hint = e instanceof Error ? e.message : "Could not reach the server.";
        const networkish =
          hint === "Failed to fetch" ||
          hint.includes("NetworkError") ||
          hint.includes("fetch resource");
        return {
          ok: false as const,
          error: networkish
            ? "Cannot reach API — start uvicorn on port 8000, restart `npm run dev`, or check firewall."
            : hint,
        };
      }
    },
    [setUserId],
  );

  const handleRegister = useCallback(
    async (username: string, password: string) => {
      try {
        const r = await apiRegister(username, password);
        if (!r.success) return { ok: false as const, error: "Username already taken." };
        return await handleLogin(username, password);
      } catch (e) {
        const hint = e instanceof Error ? e.message : "Could not reach the server.";
        const networkish =
          hint === "Failed to fetch" ||
          hint.includes("NetworkError") ||
          hint.includes("fetch resource");
        return {
          ok: false as const,
          error: networkish
            ? "Cannot reach API — start uvicorn on port 8000, restart `npm run dev`, or check firewall."
            : hint,
        };
      }
    },
    [handleLogin],
  );

  return {
    userId,
    googleAuthError,
    googleAuthPending,
    handleLogin,
    handleRegister,
    signOut,
  };
}
