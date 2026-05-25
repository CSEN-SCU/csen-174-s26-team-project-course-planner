import {
  ACADEMIC_PROGRESS_TUTORIAL_HREF,
  COURSE_PLANNER_TUTORIAL_HREF,
  DATA_DISCLOSURE_HREF,
} from "../lib/routes";

const AFFILIATION_DISCLAIMER = "Not affiliated with Santa Clara University.";

export type SiteFooterProps = {
  userId?: string | null;
  /** Opens delete-user-data flow (wipes server data + signs out). For testing; will become Log out later. */
  onDeleteUserData?: () => void;
  onOpenHelp?: () => void;
};

const linkClass =
  "text-xs font-medium text-white/90 underline-offset-2 transition hover:text-white hover:underline";
const dividerClass = "text-xs text-white/40";

export function SiteFooter({ userId, onDeleteUserData, onOpenHelp }: SiteFooterProps = {}) {
  const showDeleteUserData = Boolean(userId && onDeleteUserData);

  return (
    <footer className="site-footer relative shrink-0 px-4 py-3 text-center">
      <nav
        className="flex flex-wrap items-center justify-center gap-x-3 gap-y-1"
        aria-label="Site information"
      >
        <a href={DATA_DISCLOSURE_HREF} className={linkClass}>
          Data Disclosure
        </a>
        <span className={dividerClass} aria-hidden>
          |
        </span>
        <a href={ACADEMIC_PROGRESS_TUTORIAL_HREF} className={linkClass}>
          Academic Progress Export Tutorial
        </a>
        <span className={dividerClass} aria-hidden>
          |
        </span>
        <a href={COURSE_PLANNER_TUTORIAL_HREF} className={linkClass}>
          SCU Course Planner Tutorial
        </a>
        {showDeleteUserData && (
          <>
            <span className={dividerClass} aria-hidden>
              |
            </span>
            <button type="button" onClick={onDeleteUserData} className={linkClass}>
              Delete User Data
            </button>
          </>
        )}
      </nav>
      <p className="mt-1.5 text-[11px] leading-snug text-white/55">
        {AFFILIATION_DISCLAIMER}
      </p>
      {onOpenHelp && (
        <button
          type="button"
          onClick={onOpenHelp}
          aria-label="Open help guide"
          title="Open help guide"
          className="absolute bottom-3 right-4 flex h-8 w-8 items-center justify-center rounded-full border border-white/55 bg-white/10 text-sm font-bold text-white shadow-sm transition hover:bg-white hover:text-[var(--scu-red)] focus:outline-none focus:ring-2 focus:ring-white/80"
        >
          ?
        </button>
      )}
    </footer>
  );
}
