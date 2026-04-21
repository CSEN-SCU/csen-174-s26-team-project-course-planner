import OpenAI from "openai";
import type { PriorityMode } from "../utils/priority.js";
import { getEligibleCourseResults } from "../services/courseService.js";

const model = process.env.OPENAI_MODEL ?? "gpt-4o-mini";
const openai = process.env.OPENAI_API_KEY ? new OpenAI({ apiKey: process.env.OPENAI_API_KEY }) : null;

interface ScheduleRequest {
  selectedDesiredCourses?: string[];
  priorities?: PriorityMode;
  remainingRequirements?: string[];
  existingSchedule?: Array<{ courseCode: string; days?: string; time?: string }>;
  constraints?: { maxCourses?: number; timeWindow?: string };
}

function fallbackPlans(kind: "recommend" | "complete") {
  return [
    {
      id: `${kind}-fallback`,
      title: kind === "recommend" ? "Fallback Balanced Plan" : "Fallback Completion Plan",
      rationale: "Returned from local fallback because live OpenAI generation is unavailable.",
      source: "fallback",
      items: [] as unknown[]
    }
  ];
}

export async function generateSchedulePlans(kind: "recommend" | "complete", request: ScheduleRequest) {
  const eligible = await getEligibleCourseResults({
    completedCourses: ["CSE 30", "CSE 101", "MATH 11", "CTW 1", "CTW 2"],
    filters: { timeWindow: request.constraints?.timeWindow ?? "" },
    mode: request.priorities ?? "balanced"
  });

  if (!openai) {
    return fallbackPlans(kind).map((plan) => ({ ...plan, coursePoolSize: eligible.length }));
  }

  const prompt = [
    "You are helping build a student schedule for an SCU course-planning prototype.",
    `Task: ${kind}.`,
    `Priorities: ${request.priorities ?? "balanced"}.`,
    `Remaining requirements: ${(request.remainingRequirements ?? []).join(", ") || "none provided"}.`,
    `Existing schedule: ${JSON.stringify(request.existingSchedule ?? [])}.`,
    `Desired courses: ${(request.selectedDesiredCourses ?? []).join(", ") || "none provided"}.`,
    "Return strict JSON with shape: {\\\"plans\\\":[{\\\"id\\\":string,\\\"title\\\":string,\\\"rationale\\\":string,\\\"source\\\":\\\"openai\\\",\\\"items\\\":[{\\\"courseCode\\\":string,\\\"courseName\\\":string,\\\"days\\\":string,\\\"time\\\":string,\\\"instructor\\\":string}]}]}",
    `Eligible courses: ${JSON.stringify(eligible.slice(0, 10))}`
  ].join("\n");

  try {
    const completion = await openai.chat.completions.create({
      model,
      response_format: { type: "json_object" },
      messages: [{ role: "user", content: prompt }]
    });

    const raw = completion.choices[0]?.message?.content ?? '{"plans":[]}';
    const parsed = JSON.parse(raw) as { plans?: Array<Record<string, unknown>> };
    return (parsed.plans ?? []).map((plan, index) => ({
      id: String(plan.id ?? `${kind}-${index}`),
      title: String(plan.title ?? "AI Plan"),
      rationale: String(plan.rationale ?? "AI-generated suggestion."),
      source: "openai",
      items: Array.isArray(plan.items) ? plan.items : []
    }));
  } catch (error) {
    const fallback = fallbackPlans(kind).map((plan) => ({ ...plan, coursePoolSize: eligible.length }));
    const message = error instanceof Error ? error.message : "OpenAI request failed";
    return fallback.map((plan) => ({
      ...plan,
      rationale: `${plan.rationale} OpenAI error: ${message}`
    }));
  }
}
