/**
 * Dev: browser calls same-origin `/api/...`; Vite proxies to FastAPI (no CORS, works in Firefox).
 * Prod: set `VITE_API_BASE` (e.g. `https://api.example.com/api`) or defaults to localhost.
 */
const API_BASE =
  (import.meta.env.VITE_API_BASE as string | undefined)?.trim() ||
  (import.meta.env.DEV ? "/api" : "http://localhost:8000/api");

/**
 * Top-level navigation URL for starting Google OAuth.
 * Must point at the API origin (not the static-site origin) so the
 * deployed frontend reaches FastAPI's /auth/google/start instead of 404-ing.
 */
export function googleSignInUrl(): string {
  return `${API_BASE}/auth/google/start`;
}

function errFromBody(data: unknown): string {
  if (!data || typeof data !== "object") return "Request failed";
  const d = (data as Record<string, unknown>).detail;
  if (typeof d === "string") return d;
  if (Array.isArray(d)) {
    return d
      .map((x) =>
        typeof x === "object" && x !== null && "msg" in x
          ? String((x as { msg: unknown }).msg)
          : JSON.stringify(x),
      )
      .join("; ");
  }
  return JSON.stringify(data);
}

export async function uploadTranscript(file: File, userId?: string) {
  const formData = new FormData();
  formData.append("file", file);
  if (userId) formData.append("user_id", userId);
  const res = await fetch(`${API_BASE}/upload/transcript`, {
    method: "POST",
    body: formData,
  });
  const data = await res.json();
  if (!res.ok) throw new Error(errFromBody(data));
  return data;
}

export async function generatePlan(
  missing_details: any[],
  user_preference: string,
  user_id: string,
  previous_plan?: Record<string, unknown> | null,
  options?: {
    parsed_rows?: unknown[];
    completed_course_codes?: string[];
  },
) {
  const res = await fetch(`${API_BASE}/plan`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      missing_details,
      user_preference,
      user_id,
      previous_plan: previous_plan ?? null,
      parsed_rows: options?.parsed_rows ?? [],
      completed_course_codes: options?.completed_course_codes ?? [],
    }),
  });
  const data = await res.json();
  if (!res.ok) throw new Error(errFromBody(data));
  return data;
}

export async function getMemory(user_id: string) {
  const res = await fetch(`${API_BASE}/memory/${user_id}`);
  const data = await res.json();
  if (!res.ok) throw new Error(errFromBody(data));
  return data;
}


export async function transcribeAudio(blob: Blob): Promise<string> {
  const ext = blob.type.split("/")[1]?.split(";")[0] ?? "webm";
  const formData = new FormData();
  formData.append("file", blob, `recording.${ext}`);
  const res = await fetch(`${API_BASE}/voice/transcribe`, {
    method: "POST",
    body: formData,
  });
  const data = await res.json();
  if (!res.ok) throw new Error(errFromBody(data));
  return (data.transcript as string) ?? "";
}

export async function deleteMemory(userId: string, itemId: number) {
  const res = await fetch(`${API_BASE}/memory/${userId}/${itemId}`, { method: "DELETE" });
  const data = await res.json();
  if (!res.ok) throw new Error(errFromBody(data));
  return data;
}

export async function saveMemory(userId: string, type: string, content: string) {
  const res = await fetch(`${API_BASE}/memory/${userId}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ type, content }),
  });
  const data = await res.json();
  if (!res.ok) throw new Error(errFromBody(data));
  return data;
}

export async function generateFourYearPlan(
  missing_details: any[],
  user_id: string,
  preferences?: string,
) {
  const res = await fetch(`${API_BASE}/four-year-plan`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ missing_details, user_id, preferences: preferences ?? "" }),
  });
  const data = await res.json();
  if (!res.ok) throw new Error(errFromBody(data));
  return data;
}

/**
 * Swap the short-lived handoff token in ?google_oauth=... for the usable user_id.
 * Backend signs the token with SCU_PLANNER_COOKIE_KEY so URL tampering is rejected.
 */
export async function exchangeGoogleOauth(token: string) {
  const res = await fetch(`${API_BASE}/auth/google/exchange`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ token }),
  });
  const data = await res.json();
  if (!res.ok) throw new Error(errFromBody(data));
  return data as { success: boolean; user_id: string };
}

/** Delete user data on server: wipe memory + SQLite account (best-effort). */
export async function deleteAllUserData(userId: string) {
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), 20_000);
  try {
    const res = await fetch(`${API_BASE}/auth/user/${encodeURIComponent(userId)}/data`, {
      method: "DELETE",
      signal: controller.signal,
    });
    const text = await res.text();
    let data: unknown = {};
    try {
      data = text ? JSON.parse(text) : {};
    } catch {
      throw new Error(
        res.ok
          ? "Invalid response from server."
          : `Server error (${res.status}). Check VITE_API_BASE points at your API.`,
      );
    }
    if (!res.ok) throw new Error(errFromBody(data));
    return data as { success: boolean };
  } catch (e) {
    if (e instanceof Error && e.name === "AbortError") {
      throw new Error("Request timed out. Check that the API service is running.");
    }
    throw e;
  } finally {
    window.clearTimeout(timeout);
  }
}

export type OfferedCourse = {
  course: string;
  title: string | null;
  units: number | null;
  professor: string | null;
  meeting_days: number[];
  meeting_start_min: number | null;
  meeting_end_min: number | null;
  lab_partner: string | null;
};

/** Fetch the next-term course catalog for the manual "+ Add course" picker. */
export async function listCourses() {
  const res = await fetch(`${API_BASE}/courses`);
  const data = await res.json();
  if (!res.ok) throw new Error(errFromBody(data));
  return (data.courses as OfferedCourse[]) ?? [];
}
