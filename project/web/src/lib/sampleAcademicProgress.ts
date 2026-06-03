/**
 * Shared location + loader for the demo "sample academic progress" file.
 *
 * The file lives in `project/web/public/samples/` so it is served as a static
 * asset. To swap in a real Workday export, replace that file in place and keep
 * the same filename — no code changes required.
 */

export const SAMPLE_ACADEMIC_PROGRESS_FILENAME = "sample-academic-progress.xlsx";

/** Resolved against the app base URL so it works under a subpath deploy too. */
export const SAMPLE_ACADEMIC_PROGRESS_URL = `${import.meta.env.BASE_URL}samples/${SAMPLE_ACADEMIC_PROGRESS_FILENAME}`;

const XLSX_MIME =
  "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet";

/**
 * Fetch the bundled sample academic progress file and wrap it as a `File`
 * so it can flow through the exact same upload path as a user-picked file.
 */
export async function fetchSampleAcademicProgressFile(): Promise<File> {
  const res = await fetch(SAMPLE_ACADEMIC_PROGRESS_URL);
  if (!res.ok) {
    throw new Error(
      "The sample academic progress file is not available yet. Please try again later.",
    );
  }
  const blob = await res.blob();
  return new File([blob], SAMPLE_ACADEMIC_PROGRESS_FILENAME, { type: XLSX_MIME });
}
