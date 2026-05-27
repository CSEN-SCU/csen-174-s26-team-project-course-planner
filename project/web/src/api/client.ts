import { readSessionToken } from "../auth/session";

/**
 * Default: browser calls same-origin `/api/...`.
 * - Dev: Vite proxies `/api` → FastAPI (see `vite.config.ts`)
 * - Prod: a reverse proxy / rewrite should route `/api` → FastAPI
 *
 * If your API is hosted on a different origin, set `VITE_API_BASE`
 * (e.g. `https://api.example.com/api`).
 */
const API_BASE =
  (import.meta.env.VITE_API_BASE as string | undefined)?.trim() ||
  "/api";

/**
 * Top-level navigation URL for starting Google OAuth.
 * Must point at the API origin (not the static-site origin) so the
 * deployed frontend reaches FastAPI's /auth/google/start instead of 404-ing.
 */
export function googleSignInUrl(): string {
  return `${API_BASE}/auth/google/start`;
}

function authHeaders(extra?: Record<string, string>): Record<string, string> {
  const headers: Record<string, string> = { ...extra };
  const token = readSessionToken();
  if (token) headers.Authorization = `Bearer ${token}`;
  return headers;
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
  // Structured rate-limit error: { detail: { error: "rate_limited", retry_after_seconds: N } }
  if (d && typeof d === "object" && (d as Record<string, unknown>).error === "rate_limited") {
    const wait = (d as Record<string, unknown>).retry_after_seconds;
    return `Too many requests — please wait ${wait} second${wait === 1 ? "" : "s"} and try again.`;
  }
  return JSON.stringify(data);
}

export async function uploadTranscript(file: File, userId?: string) {
  const formData = new FormData();
  formData.append("file", file);
  if (userId) formData.append("user_id", userId);
  const res = await fetch(`${API_BASE}/upload/transcript`, {
    method: "POST",
    headers: authHeaders(),
    body: formData,
  });
  const data = await res.json();
  if (!res.ok) throw new Error(errFromBody(data));
  return data;
}

/**
 * Set VITE_USE_PLAN_V2=1 to route the plan request through the LangGraph
 * multi-agent engine (POST /api/plan/v2) instead of the legacy single-shot
 * planner (POST /api/plan).  Both endpoints return the same response shape so
 * the rest of the UI requires no changes.
 */
const _USE_PLAN_V2 = (import.meta.env.VITE_USE_PLAN_V2 as string | undefined) === "1";

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
  const endpoint = _USE_PLAN_V2 ? `${API_BASE}/plan/v2` : `${API_BASE}/plan`;
  const res = await fetch(endpoint, {
    method: "POST",
    headers: authHeaders({ "Content-Type": "application/json" }),
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
  const res = await fetch(`${API_BASE}/memory/${user_id}`, {
    headers: authHeaders(),
  });
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
  const res = await fetch(`${API_BASE}/memory/${userId}/${itemId}`, {
    method: "DELETE",
    headers: authHeaders(),
  });
  const data = await res.json();
  if (!res.ok) throw new Error(errFromBody(data));
  return data;
}

export async function saveMemory(userId: string, type: string, content: string) {
  const res = await fetch(`${API_BASE}/memory/${userId}`, {
    method: "POST",
    headers: authHeaders({ "Content-Type": "application/json" }),
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
    headers: authHeaders({ "Content-Type": "application/json" }),
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
  return data as { success: boolean; user_id: string; session_token?: string };
}

/** Delete user data on server: wipe memory + SQLite account (best-effort). */
export async function deleteAllUserData(userId: string) {
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), 20_000);
  try {
    const res = await fetch(`${API_BASE}/auth/user/${encodeURIComponent(userId)}/data`, {
      headers: authHeaders(),
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

export type CatalogSection = {
  course_section: string;
  course: string;
  section: number;
  subject: string;
  number: string;
  title: string | null;
  units: number | null;
  status: string | null;
  enrolled_capacity: string | null;
  instructors: string[];
  meeting_days: number[];
  meeting_start_min: number | null;
  meeting_end_min: number | null;
  meeting_pattern: string | null;
  location: string | null;
  course_tags: string[];
  lab_partner: string | null;
  /** Best instructor on the section (Rate My Professor). */
  instructor_display?: string | null;
  instructor_rating?: number | null;
  instructor_difficulty?: number | null;
  instructor_wta_pct?: number | null;
  instructor_rating_source?: string | null;
  instructor_balanced_score?: number | null;
};

export type CatalogMeetingTimeSlot = {
  id: string;
  label: string;
  window_start_min: number;
  window_end_min: number;
  min_overlap_min?: number;
};

export type CatalogFacets = {
  subjects: string[];
  tags: { Core: string[]; Other: string[] };
  meeting_times: CatalogMeetingTimeSlot[];
};

export type CourseBrowserLaunchContext =
  | { mode: "open" }
  | { mode: "slot"; dayIndex: number; startMin: number; endMin: number; label: string };

export type CatalogSearchParams = {
  q?: string;
  subject?: string[];
  days?: number[];
  meeting_time?: string[];
  tag?: string[];
  day_index?: number;
  start_min?: number;
  end_min?: number;
  limit?: number;
  offset?: number;
  sort?: "default" | "rating" | "difficulty" | "balanced";
};

export async function searchCatalogSections(params: CatalogSearchParams = {}) {
  const q = new URLSearchParams();
  if (params.q?.trim()) q.set("q", params.q.trim());
  if (params.subject?.length) q.set("subject", params.subject.join(","));
  if (params.days?.length) q.set("days", params.days.join(","));
  if (params.meeting_time?.length) q.set("meeting_time", params.meeting_time.join(","));
  if (params.tag?.length) q.set("tag", params.tag.join(","));
  if (params.day_index != null) q.set("day_index", String(params.day_index));
  if (params.start_min != null) q.set("start_min", String(params.start_min));
  if (params.end_min != null) q.set("end_min", String(params.end_min));
  if (params.limit != null) q.set("limit", String(params.limit));
  if (params.offset != null) q.set("offset", String(params.offset));
  if (params.sort && params.sort !== "default") q.set("sort", params.sort);
  const qs = q.toString();
  const res = await fetch(`${API_BASE}/catalog/sections${qs ? `?${qs}` : ""}`);
  const data = await res.json();
  if (!res.ok) throw new Error(errFromBody(data));
  return data as {
    sections: CatalogSection[];
    total: number;
    count: number;
    facets: CatalogFacets;
  };
}

// ── Slot-based course suggestions (R6) ──────────────────────────────────────

export type CourseSuggestion = {
  course: string;
  title: string;
  units: number;
  instructor: string;
  rating: number;
  difficulty: number;
  would_take_again_pct?: number | null;
  source?: string | null;
  quality?: number;
  rationale: string;
  covers?: string[];
  kind?: "requirement" | "enrichment";
  meeting_days?: number[];
  meeting_start_min?: number | null;
  meeting_end_min?: number | null;
};

export type EnrichmentSlotSuggestions = {
  track_label: string;
  subjects: string[];
  prompt: string | null;
  candidates: CourseSuggestion[];
};

/** Suggest courses for a calendar time slot (R6 popover). */
export async function suggestCoursesForSlot(params: {
  day_index: number;
  start_min: number;
  end_min: number;
  missing_details: Record<string, unknown>[];
  exclude_codes?: string[];
  /** Recent chat text — used to infer enrichment direction (e.g. 中文). */
  user_preference?: string;
}) {
  const res = await fetch(`${API_BASE}/plan/suggest_for_slot`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      day_index: params.day_index,
      start_min: params.start_min,
      end_min: params.end_min,
      missing_details: params.missing_details,
      exclude_codes: params.exclude_codes ?? [],
      user_preference: params.user_preference ?? "",
    }),
  });
  const data = await res.json();
  if (!res.ok) throw new Error(errFromBody(data));
  return {
    candidates: (data.candidates as CourseSuggestion[]) ?? [],
    count: data.count as number,
    message: typeof data.message === "string" ? data.message : undefined,
    enrichment: (data.enrichment as EnrichmentSlotSuggestions | null | undefined) ?? null,
  };
}
