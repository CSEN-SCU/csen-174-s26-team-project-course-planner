import { googleSignInUrl } from "../api/client";
import { BrandLink } from "./BrandLink";

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
  sessions: MemorySessionRow[];
  activeSessionId: string | null;
  onSelectSession: (row: MemorySessionRow) => void;
  onDeleteSession?: (id: string) => void;
  onNewPlan: () => void;
  /** Error from out-of-band auth flows (e.g. Google OAuth callback). */
  externalAuthError?: string | null;
  /** True while finishing Google sign-in (show loading state instead of the sign-in button). */
  authPending?: boolean;
};

export function LeftPanel({
  userId,
  sessions,
  activeSessionId,
  onSelectSession,
  onDeleteSession,
  onNewPlan,
  externalAuthError,
  authPending = false,
}: LeftPanelProps) {
  return (
    <aside className="flex w-[260px] shrink-0 flex-col border-l-4 border-[var(--scu-red)] bg-[var(--scu-white)] shadow-sm">
      <div className="border-b border-neutral-200 px-4 py-5">
        <BrandLink />
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

      {!userId && !authPending ? (
        <div className="min-h-0 flex-1 overflow-y-auto px-4 pb-4">
          {externalAuthError && (
            <p className="mb-2 rounded border border-red-200 bg-red-50 px-2 py-1.5 text-xs text-red-700">
              {externalAuthError}
            </p>
          )}
          <a
            href={googleSignInUrl()}
            className="flex w-full items-center justify-center gap-2 rounded-md border border-neutral-300 bg-white px-3 py-2 text-sm font-semibold text-neutral-700 shadow-sm transition hover:bg-neutral-50"
          >
            <svg width="16" height="16" viewBox="0 0 18 18" aria-hidden>
              <path fill="#4285F4" d="M17.64 9.2c0-.64-.06-1.25-.16-1.84H9v3.48h4.84a4.14 4.14 0 0 1-1.8 2.72v2.26h2.92c1.71-1.58 2.68-3.9 2.68-6.62z"/>
              <path fill="#34A853" d="M9 18c2.43 0 4.47-.8 5.96-2.18l-2.92-2.26c-.8.54-1.84.86-3.04.86-2.34 0-4.32-1.58-5.03-3.7H.96v2.34A9 9 0 0 0 9 18z"/>
              <path fill="#FBBC05" d="M3.97 10.72A5.4 5.4 0 0 1 3.68 9c0-.6.1-1.18.29-1.72V4.94H.96A9 9 0 0 0 0 9c0 1.45.35 2.82.96 4.06l3.01-2.34z"/>
              <path fill="#EA4335" d="M9 3.58c1.32 0 2.5.45 3.44 1.35l2.58-2.58A9 9 0 0 0 9 0 9 9 0 0 0 .96 4.94l3.01 2.34C4.68 5.16 6.66 3.58 9 3.58z"/>
            </svg>
            Continue with Google
          </a>
        </div>
      ) : (
        <div className="min-h-0 flex-1 overflow-y-auto px-2 pb-4">
          {authPending && !userId ? (
            <p className="px-2 py-3 text-sm text-neutral-500">Signing in with Google…</p>
          ) : (
          <>
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
          </>
          )}
        </div>
      )}
    </aside>
  );
}
