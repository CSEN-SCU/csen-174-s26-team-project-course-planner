import { FormEvent, useState } from "react";

export type UsernameAuthPanelProps = {
  onLogin: (username: string, password: string) => Promise<{ ok: boolean; error?: string }>;
  onRegister: (username: string, password: string) => Promise<{ ok: boolean; error?: string }>;
};

export function UsernameAuthPanel({ onLogin, onRegister }: UsernameAuthPanelProps) {
  const [tab, setTab] = useState<"login" | "register">("login");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);

  const switchTab = (t: "login" | "register") => {
    setTab(t);
    setError(null);
    setSuccessMsg(null);
    setPassword("");
    setConfirmPassword("");
  };

  const submitLogin = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      const r = await onLogin(username.trim(), password);
      if (!r.ok) setError(r.error ?? "Login failed.");
      else setPassword("");
    } finally {
      setBusy(false);
    }
  };

  const submitRegister = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    setSuccessMsg(null);
    if (password !== confirmPassword) {
      setError("Passwords do not match.");
      return;
    }
    if (!/^[A-Za-z0-9_.\-]{3,32}$/.test(username.trim())) {
      setError("Username must be 3–32 chars: letters, digits, dot, underscore, or hyphen.");
      return;
    }
    if (password.length < 8) {
      setError("Password must be at least 8 characters.");
      return;
    }
    setBusy(true);
    try {
      const r = await onRegister(username.trim(), password);
      if (!r.ok) setError(r.error ?? "Registration failed.");
      else {
        setPassword("");
        setConfirmPassword("");
        setSuccessMsg("Account created — you are now logged in.");
      }
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="w-full max-w-xs">
      <div className="mb-3 flex rounded-md border border-neutral-200 p-0.5">
        <button
          type="button"
          onClick={() => switchTab("login")}
          className={`flex-1 rounded py-1.5 text-xs font-semibold transition ${
            tab === "login"
              ? "bg-[var(--scu-red)] text-white"
              : "text-neutral-500 hover:text-neutral-700"
          }`}
        >
          Log in
        </button>
        <button
          type="button"
          onClick={() => switchTab("register")}
          className={`flex-1 rounded py-1.5 text-xs font-semibold transition ${
            tab === "register"
              ? "bg-[var(--scu-red)] text-white"
              : "text-neutral-500 hover:text-neutral-700"
              }`}
        >
          Register
        </button>
      </div>

      {tab === "login" ? (
        <form onSubmit={submitLogin} className="space-y-2">
          <input
            type="text"
            autoComplete="username"
            placeholder="Username"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            className="w-full rounded-md border border-neutral-300 px-3 py-2 text-sm text-[var(--scu-text)] outline-none focus:border-[var(--scu-red)] focus:ring-1 focus:ring-[var(--scu-red)]"
          />
          <input
            type="password"
            autoComplete="current-password"
            placeholder="Password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="w-full rounded-md border border-neutral-300 px-3 py-2 text-sm text-[var(--scu-text)] outline-none focus:border-[var(--scu-red)] focus:ring-1 focus:ring-[var(--scu-red)]"
          />
          <button
            type="submit"
            disabled={busy}
            className="w-full rounded-md bg-[var(--scu-red)] px-3 py-2 text-sm font-semibold text-white shadow-sm transition hover:bg-[var(--scu-dark-red)] disabled:opacity-60"
          >
            {busy ? "…" : "Log in"}
          </button>
          {error && <p className="text-xs text-red-600">{error}</p>}
        </form>
      ) : (
        <form onSubmit={submitRegister} className="space-y-2">
          <input
            type="text"
            autoComplete="username"
            placeholder="Username"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            className="w-full rounded-md border border-neutral-300 px-3 py-2 text-sm text-[var(--scu-text)] outline-none focus:border-[var(--scu-red)] focus:ring-1 focus:ring-[var(--scu-red)]"
          />
          <input
            type="password"
            autoComplete="new-password"
            placeholder="Password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="w-full rounded-md border border-neutral-300 px-3 py-2 text-sm text-[var(--scu-text)] outline-none focus:border-[var(--scu-red)] focus:ring-1 focus:ring-[var(--scu-red)]"
          />
          <input
            type="password"
            autoComplete="new-password"
            placeholder="Confirm password"
            value={confirmPassword}
            onChange={(e) => setConfirmPassword(e.target.value)}
            className="w-full rounded-md border border-neutral-300 px-3 py-2 text-sm text-[var(--scu-text)] outline-none focus:border-[var(--scu-red)] focus:ring-1 focus:ring-[var(--scu-red)]"
          />
          <button
            type="submit"
            disabled={busy}
            className="w-full rounded-md bg-[var(--scu-red)] px-3 py-2 text-sm font-semibold text-white shadow-sm transition hover:bg-[var(--scu-dark-red)] disabled:opacity-60"
          >
            {busy ? "…" : "Create account"}
          </button>
          {error && <p className="text-xs text-red-600">{error}</p>}
          {successMsg && <p className="text-xs text-green-600">{successMsg}</p>}
        </form>
      )}
    </div>
  );
}
