import type { CatalogSection } from "../api/client";

type RatingFields = Pick<
  CatalogSection,
  | "instructor_rating"
  | "instructor_difficulty"
  | "instructor_wta_pct"
  | "instructor_display"
  | "instructor_rating_source"
>;

function StarIcon() {
  return (
    <svg
      className="h-3 w-3 shrink-0 text-amber-500"
      viewBox="0 0 20 20"
      fill="currentColor"
      aria-hidden
    >
      <path d="M9.049 2.927c.3-.921 1.603-.921 1.902 0l1.07 3.292a1 1 0 00.95.69h3.462c.969 0 1.371 1.24.588 1.81l-2.8 2.034a1 1 0 00-.364 1.118l1.07 3.292c.3.921-.755 1.688-1.54 1.118l-2.8-2.034a1 1 0 00-1.175 0l-2.8 2.034c-.784.57-1.838-.197-1.539-1.118l1.07-3.292a1 1 0 00-.364-1.118L2.98 8.72c-.783-.57-.38-1.81.588-1.81h3.461a1 1 0 00.951-.69l1.07-3.292z" />
    </svg>
  );
}

export type CatalogSortMode = "default" | "rating" | "difficulty" | "balanced";

export const CATALOG_SORT_OPTIONS: { value: CatalogSortMode; label: string }[] = [
  { value: "default", label: "Course order" },
  { value: "rating", label: "Professor quality" },
  { value: "difficulty", label: "Easier first" },
  { value: "balanced", label: "Quality + easiness" },
];

export function InstructorRatingLine({
  section,
  showInstructor = true,
  className = "",
}: {
  section: RatingFields;
  showInstructor?: boolean;
  className?: string;
}) {
  const rating = section.instructor_rating;
  const difficulty = section.instructor_difficulty;
  const wta = section.instructor_wta_pct;
  const name = section.instructor_display;

  if (rating == null && difficulty == null) {
    return (
      <p className={`text-[11px] text-neutral-400 ${className}`.trim()}>
        No Rate My Professor rating
        {showInstructor && name ? ` · ${name}` : ""}
      </p>
    );
  }

  return (
    <p
      className={`flex flex-wrap items-center gap-x-1.5 gap-y-0.5 text-[11px] text-neutral-600 ${className}`.trim()}
      title="Ratings from Rate My Professor"
    >
      {rating != null && (
        <span className="inline-flex items-center gap-0.5 font-medium text-neutral-800">
          <StarIcon />
          <span>{rating.toFixed(1)}</span>
          <span className="font-normal text-neutral-500">quality</span>
        </span>
      )}
      {rating != null && difficulty != null && (
        <span className="text-neutral-300" aria-hidden>
          ·
        </span>
      )}
      {difficulty != null && (
        <span>
          <span className="font-medium text-neutral-800">{difficulty.toFixed(1)}</span>
          <span className="text-neutral-500"> difficulty</span>
        </span>
      )}
      {wta != null && (
        <>
          <span className="text-neutral-300" aria-hidden>
            ·
          </span>
          <span className="text-neutral-500">{Math.round(wta)}% would take again</span>
        </>
      )}
      {showInstructor && name && (
        <>
          <span className="text-neutral-300" aria-hidden>
            ·
          </span>
          <span className="truncate text-neutral-500" title={name}>
            {name}
          </span>
        </>
      )}
      <span className="sr-only">Source: Rate My Professor</span>
    </p>
  );
}
