import {
  ACADEMIC_PROGRESS_TUTORIAL_HREF,
  COURSE_PLANNER_TUTORIAL_HREF,
  DATA_DISCLOSURE_HREF,
} from "../lib/routes";

const UNOFFICIAL_DISCLAIMER =
  "Unofficial student project — not affiliated with Santa Clara University.";

export type SiteFooterProps = {
  userId?: string | null;
  onDeleteUserData?: () => void;
};

export function SiteFooter({ userId, onDeleteUserData }: SiteFooterProps = {}) {
  const showDelete = Boolean(userId && onDeleteUserData);

  return (
    <footer className="shrink-0 border-t border-neutral-200 bg-white px-4 py-3 text-center">
      <nav
        className="flex flex-wrap items-center justify-center gap-x-3 gap-y-1"
        aria-label="Site information"
      >
        <a
          href={DATA_DISCLOSURE_HREF}
          className="text-sm font-semibold text-neutral-700 underline-offset-2 transition hover:text-[var(--scu-red)] hover:underline"
        >
          Data Disclosure
        </a>
        <span className="text-xs text-neutral-300" aria-hidden>
          |
        </span>
        <a
          href={ACADEMIC_PROGRESS_TUTORIAL_HREF}
          className="text-xs font-medium text-neutral-500 underline-offset-2 transition hover:text-[var(--scu-red)] hover:underline"
        >
          Academic Progress Export Tutorial
        </a>
        <span className="text-xs text-neutral-300" aria-hidden>
          |
        </span>
        <a
          href={COURSE_PLANNER_TUTORIAL_HREF}
          className="text-xs font-medium text-neutral-500 underline-offset-2 transition hover:text-[var(--scu-red)] hover:underline"
        >
          SCU Course Planner Tutorial
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
      <p className="mt-1.5 text-[11px] leading-snug text-neutral-400">
        {UNOFFICIAL_DISCLAIMER}
      </p>
    </footer>
  );
}
