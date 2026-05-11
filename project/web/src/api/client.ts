/**
 * Dev: browser calls same-origin `/api/...`; Vite proxies to FastAPI (no CORS, works in Firefox).
 * Prod: set `VITE_API_BASE` (e.g. `https://api.example.com/api`) or defaults to localhost.
 */
const API_BASE =
  (import.meta.env.VITE_API_BASE as string | undefined)?.trim() ||
  (import.meta.env.DEV ? "/api" : "http://localhost:8000/api");

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
) {
  const res = await fetch(`${API_BASE}/plan`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ missing_details, user_preference, user_id, previous_plan: previous_plan ?? null }),
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

export async function login(username: string, password: string) {
  const res = await fetch(`${API_BASE}/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password }),
  });
  const data = await res.json();
  if (!res.ok) throw new Error(errFromBody(data));
  return data;
}
