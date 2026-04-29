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

export interface AiStatus {
  aiProvider: string;
  aiModel: string;
  aiEnabled: boolean;
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

function normalizeMeetingDays(days: string): string {
  return days === "MW" ? "MWF" : days;
}

function toScheduledItem(item: Record<string, unknown>, index: number): ScheduledItem {
  return {
    courseId: `ai-${index}-${String(item.courseCode ?? "course")}`,
    courseCode: String(item.courseCode ?? "TBD"),
    courseName: String(item.courseName ?? "Suggested Course"),
    sectionId: String(item.sectionId ?? `ai-section-${index}`),
    instructor: String(item.instructor ?? "TBD"),
    days: normalizeMeetingDays(String(item.days ?? "TBD")),
    time: String(item.time ?? "TBD"),
    quality: Number(item.quality ?? 0),
    difficulty: Number(item.difficulty ?? 0)
  };
}

export async function chatWithAi(payload: {
  message: string;
  completedCourses: string[];
  priorities: PriorityMode;
  remainingRequirements: string[];
  existingSchedule: ScheduledItem[];
}): Promise<{ answer: string; source: string }> {
  const result = await requestJson<{ answer?: string; source?: string }>("/schedule/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload)
  });
  return {
    answer: String(result.answer ?? "I could not generate a response."),
    source: String(result.source ?? "unknown")
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

export async function previewSchedule(payload: {
  selectedDesiredCourses: string[];
  completedCourses: string[];
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
    id: String(plan.id ?? `preview-${index}`),
    title: String(plan.title ?? "Preview Plan"),
    rationale: String(plan.rationale ?? "AI-generated schedule preview"),
    source: String(plan.source ?? "unknown"),
    items: Array.isArray(plan.items) ? plan.items.map((item, itemIndex) => toScheduledItem(item as Record<string, unknown>, itemIndex)) : []
  }));
}

export async function getAiStatus(): Promise<AiStatus> {
  const health = await requestJson<{ aiProvider?: string; aiModel?: string; aiEnabled?: boolean }>("/health");
  return {
    aiProvider: health.aiProvider ?? "OpenAI",
    aiModel: health.aiModel ?? "gpt-4o-mini",
    aiEnabled: Boolean(health.aiEnabled)
  };
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
