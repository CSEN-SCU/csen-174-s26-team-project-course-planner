export type SiteFooterProps = {
  userId?: string | null;
  onDeleteUserData?: () => void;
};

export function SiteFooter({ userId, onDeleteUserData }: SiteFooterProps = {}) {
  const showDelete = Boolean(userId && onDeleteUserData);

  return (
    <footer className="shrink-0 border-t border-neutral-200 bg-white py-2.5 text-center">
      <nav
        className="flex flex-wrap items-center justify-center gap-x-3 gap-y-1 px-4"
        aria-label="Site information"
      >
        <a
          href="#/data-disclosure"
          className="text-xs font-medium text-neutral-500 underline-offset-2 transition hover:text-[var(--scu-red)] hover:underline"
        >
          Data Disclosure
        </a>
        <span className="text-xs text-neutral-300" aria-hidden>
          |
        </span>
        <a
          href="#/academic-progress-export-tutorial"
          className="text-xs font-medium text-neutral-500 underline-offset-2 transition hover:text-[var(--scu-red)] hover:underline"
        >
          Academic Progress Export Tutorial
        </a>
        {showDelete && (
          <>
            <span className="text-xs text-neutral-300" aria-hidden>
              |
            </span>
            <button
              type="button"
              onClick={onDeleteUserData}
              className="text-xs font-medium text-neutral-500 underline-offset-2 transition hover:text-[var(--scu-red)] hover:underline"
            >
              Delete User Data
            </button>
          </>
        )}
      </nav>
    </footer>
  );
}
