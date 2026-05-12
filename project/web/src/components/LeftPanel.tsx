import { FormEvent, useState } from "react";

export type MemorySessionRow = {
  id: string;
  title: string;
  dateLabel: string;
  kind: "memory" | "snapshot" | "current";
  memoryContent?: string;
  recommended?: Record<string, unknown>[];
  messages?: { id: string; role: string; content: string }[];
};

export type LeftPanelProps = {
  userId: string | null;
  onLogin: (username: string, password: string) => Promise<{ ok: boolean; error?: string }>;
  onRegister: (username: string, password: string) => Promise<{ ok: boolean; error?: string }>;
  sessions: MemorySessionRow[];
  activeSessionId: string | null;
  onSelectSession: (row: MemorySessionRow) => void;
  onDeleteSession?: (id: string) => void;
  onNewPlan: () => void;
};

export function LeftPanel({
  userId,
  onLogin,
  onRegister,
  sessions,
  activeSessionId,
  onSelectSession,
  onDeleteSession,
  onNewPlan,
}: LeftPanelProps) {
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
    <aside className="flex w-[260px] shrink-0 flex-col border-l-4 border-[var(--scu-red)] bg-[var(--scu-white)] shadow-sm">
      <div className="border-b border-neutral-200 px-4 py-5">
        <div className="flex items-baseline gap-1">
          <span className="text-2xl font-bold tracking-tight text-[var(--scu-red)]">
            SCU
          </span>
          <span className="text-sm font-medium text-neutral-500">
            Course Planner
          </span>
        </div>
      </div>

      <div className="px-4 py-4">
        <button
          type="button"
          onClick={onNewPlan}
          className="w-full rounded-md bg-[var(--scu-red)] px-3 py-2.5 text-sm font-semibold text-white shadow-sm transition hover:bg-[var(--scu-dark-red)]"
        >
          New Plan
        </button>
      </div>

      {!userId ? (
        <div className="min-h-0 flex-1 overflow-y-auto px-4 pb-4">
          {/* Tab toggle */}
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
      ) : (
        <div className="min-h-0 flex-1 overflow-y-auto px-2 pb-4">
          <p className="px-2 pb-2 text-xs font-semibold uppercase tracking-wide text-neutral-400">
            Past sessions
          </p>
          <ul className="space-y-1">
            {sessions.map((s) => {
              const active = s.id === activeSessionId;
              return (
                <li key={s.id} className="group relative">
                  <button
                    type="button"
                    onClick={() => onSelectSession(s)}
                    className={`w-full rounded-md px-3 py-2.5 pr-8 text-left text-sm transition ${
                      active
                        ? "bg-[var(--scu-gray)] font-medium text-[var(--scu-text)] ring-1 ring-neutral-200"
                        : "text-neutral-700 hover:bg-neutral-50"
                    }`}
                  >
                    <span className="block truncate">{s.title}</span>
                    <span className="mt-0.5 block text-xs text-neutral-500">
                      {s.dateLabel}
                    </span>
                  </button>
                  {onDeleteSession && s.kind !== "current" && (
                    <button
                      type="button"
                      onClick={(e) => { e.stopPropagation(); onDeleteSession(s.id); }}
                      className="absolute right-1.5 top-1/2 -translate-y-1/2 rounded p-1 text-neutral-300 opacity-0 group-hover:opacity-100 hover:text-red-500 hover:bg-red-50 transition"
                      aria-label={`Delete ${s.title}`}
                    >
                      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" aria-hidden>
                        <path d="M18 6L6 18M6 6l12 12" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round"/>
                      </svg>
                    </button>
                  )}
                </li>
              );
            })}
          </ul>
        </div>
      )}
    </aside>
  );
}
