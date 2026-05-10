import { FormEvent, useState } from "react";

export type MemorySessionRow = {
  id: string;
  title: string;
  dateLabel: string;
  kind: "memory" | "snapshot" | "current";
  memoryContent?: string;
  recommended?: Record<string, unknown>[];
};

export type LeftPanelProps = {
  userId: string | null;
  onLogin: (username: string, password: string) => Promise<{ ok: boolean; error?: string }>;
  sessions: MemorySessionRow[];
  activeSessionId: string | null;
  onSelectSession: (row: MemorySessionRow) => void;
  onNewPlan: () => void;
};

export function LeftPanel({
  userId,
  onLogin,
  sessions,
  activeSessionId,
  onSelectSession,
  onNewPlan,
}: LeftPanelProps) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [loginError, setLoginError] = useState<string | null>(null);

  const submitLogin = async (e: FormEvent) => {
    e.preventDefault();
    setLoginError(null);
    setBusy(true);
    try {
      const r = await onLogin(username.trim(), password);
      if (!r.ok) setLoginError(r.error ?? "Login failed.");
      else {
        setPassword("");
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
          <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-neutral-400">
            Log in
          </p>
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
            {loginError ? (
              <p className="text-xs text-red-600">{loginError}</p>
            ) : null}
          </form>
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
                <li key={s.id}>
                  <button
                    type="button"
                    onClick={() => onSelectSession(s)}
                    className={`w-full rounded-md px-3 py-2.5 text-left text-sm transition ${
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
                </li>
              );
            })}
          </ul>
        </div>
      )}
    </aside>
  );
}
