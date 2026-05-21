/**
 * Client-side routes for the static SPA (Render, Vite preview, etc.).
 *
 * Prefer HASH_*_HREF for in-app links. Hash routing avoids Render 404s
 * on deep links without a `/* → /index.html` rewrite rule.
 */
export const DATA_DISCLOSURE_PATH = "/data-disclosure";
export const ACADEMIC_PROGRESS_TUTORIAL_PATH = "/academic-progress-export-tutorial";
export const COURSE_PLANNER_TUTORIAL_PATH = "/course-planner-tutorial";

export const DATA_DISCLOSURE_HREF = "#/data-disclosure";
export const ACADEMIC_PROGRESS_TUTORIAL_HREF = "#/academic-progress-export-tutorial";
export const COURSE_PLANNER_TUTORIAL_HREF = "#/course-planner-tutorial";

const HASH_ROUTES: Record<string, string> = {
  "data-disclosure": DATA_DISCLOSURE_PATH,
  "academic-progress-export-tutorial": ACADEMIC_PROGRESS_TUTORIAL_PATH,
  "course-planner-tutorial": COURSE_PLANNER_TUTORIAL_PATH,
};

const PATH_ROUTES: Record<string, string> = {
  [DATA_DISCLOSURE_PATH]: DATA_DISCLOSURE_PATH,
  [ACADEMIC_PROGRESS_TUTORIAL_PATH]: ACADEMIC_PROGRESS_TUTORIAL_PATH,
  [COURSE_PLANNER_TUTORIAL_PATH]: COURSE_PLANNER_TUTORIAL_PATH,
};

export function resolveClientRoute(): string {
  const hash = window.location.hash.replace(/^#\/?/, "");
  if (hash && HASH_ROUTES[hash]) {
    return HASH_ROUTES[hash];
  }
  const trimmed = window.location.pathname.replace(/\/+$/, "");
  const path = trimmed === "" ? "/" : trimmed;
  return PATH_ROUTES[path] ?? path;
}
