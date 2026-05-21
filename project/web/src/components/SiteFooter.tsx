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

const linkClass =
  "text-xs font-medium text-white/90 underline-offset-2 transition hover:text-white hover:underline";
const primaryLinkClass =
  "text-sm font-semibold text-white underline-offset-2 transition hover:text-white/80 hover:underline";
const dividerClass = "text-xs text-white/40";

export function SiteFooter({ userId, onDeleteUserData }: SiteFooterProps = {}) {
  const showDelete = Boolean(userId && onDeleteUserData);

  return (
    <footer className="site-footer shrink-0 px-4 py-3 text-center">
      <nav
        className="flex flex-wrap items-center justify-center gap-x-3 gap-y-1"
        aria-label="Site information"
      >
        <a href={DATA_DISCLOSURE_HREF} className={primaryLinkClass}>
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
        {showDelete && (
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
        {UNOFFICIAL_DISCLAIMER}
      </p>
    </footer>
  );
}
