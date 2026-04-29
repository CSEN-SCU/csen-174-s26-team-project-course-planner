import type { AiRecommendation, CourseResult, Filters, PriorityMode, ScheduledItem, TranscriptSummary } from "../types/domain";

const API_BASE = import.meta.env.VITE_API_URL ?? "http://localhost:8080";

interface ApiError {
  error?: string;
}

interface TranscriptSummaryApiResponse extends TranscriptSummary {
  source?: string;
}

interface IcsResponse {
  filename: string;
  content: string;
  conflicts: Array<{ courseCode: string; conflictsWith: string }>;
}

async function requestJson<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, options);
  if (!response.ok) {
    let message = `Request failed (${response.status})`;
    try {
      const body = (await response.json()) as ApiError;
      if (body.error) message = body.error;
    } catch {
      // No-op fallback message
    }
    throw new Error(message);
  }
  return (await response.json()) as T;
}

function toScheduledItem(item: Record<string, unknown>, index: number): ScheduledItem {
  return {
    courseId: `ai-${index}-${String(item.courseCode ?? "course")}`,
    courseCode: String(item.courseCode ?? "TBD"),
    courseName: String(item.courseName ?? "Suggested Course"),
    sectionId: String(item.sectionId ?? `ai-section-${index}`),
    instructor: String(item.instructor ?? "TBD"),
    days: String(item.days ?? "TBD"),
    time: String(item.time ?? "TBD")
  };
}

export async function parseTranscript(payload: { fileName?: string; transcriptText?: string }): Promise<TranscriptSummaryApiResponse> {
  return requestJson<TranscriptSummaryApiResponse>("/transcript/parse", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload)
  });
}

export async function getEligibleCourses(
  filters: Filters,
  mode: PriorityMode,
  completedCourses: string[]
): Promise<CourseResult[]> {
  return requestJson<CourseResult[]>("/courses/eligible", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ filters, mode, completedCourses })
  });
}

export async function recommendSchedule(payload: {
  selectedDesiredCourses: string[];
  priorities: PriorityMode;
  remainingRequirements: string[];
  existingSchedule: ScheduledItem[];
  constraints?: { maxCourses?: number; timeWindow?: string };
}): Promise<AiRecommendation[]> {
  const plans = await requestJson<Array<Record<string, unknown>>>("/schedule/recommend", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload)
  });
  return plans.map((plan, index) => ({
    id: String(plan.id ?? `recommend-${index}`),
    title: String(plan.title ?? "Recommended Plan"),
    rationale: String(plan.rationale ?? "AI-generated recommendation"),
    items: Array.isArray(plan.items) ? plan.items.map((item, itemIndex) => toScheduledItem(item as Record<string, unknown>, itemIndex)) : []
  }));
}

export async function completeSchedule(payload: {
  selectedDesiredCourses: string[];
  priorities: PriorityMode;
  remainingRequirements: string[];
  existingSchedule: ScheduledItem[];
  constraints?: { maxCourses?: number; timeWindow?: string };
}): Promise<AiRecommendation[]> {
  const plans = await requestJson<Array<Record<string, unknown>>>("/schedule/complete", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload)
  });
  return plans.map((plan, index) => ({
    id: String(plan.id ?? `complete-${index}`),
    title: String(plan.title ?? "Completed Plan"),
    rationale: String(plan.rationale ?? "AI-generated completion"),
    items: Array.isArray(plan.items) ? plan.items.map((item, itemIndex) => toScheduledItem(item as Record<string, unknown>, itemIndex)) : []
  }));
}

export async function exportIcs(scheduleItems: ScheduledItem[]): Promise<void> {
  const items = scheduleItems.map((item) => {
    const [startTime = "09:00", endTime = "10:00"] = item.time.split("-");
    return {
      courseCode: item.courseCode,
      courseName: item.courseName,
      days: item.days,
      startTime,
      endTime,
      instructor: item.instructor
    };
  });

  const response = await requestJson<IcsResponse>("/schedule/export-ics", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ items })
  });

  const blob = new Blob([response.content], { type: "text/calendar;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = response.filename || "bronco-plan.ics";
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}
