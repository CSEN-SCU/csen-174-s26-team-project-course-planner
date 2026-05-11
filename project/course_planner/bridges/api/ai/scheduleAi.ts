import { getEligibleCourseResults } from "../services/courseService.js";

type ProviderName = "gemini" | "fallback";
type PriorityMode = "balanced" | "quality" | "easy";

const DEFAULT_GEMINI_MODEL = "gemini-2.5-flash-lite";
const DEFAULT_GEMINI_BASE_URL = "https://generativelanguage.googleapis.com";

function truthyEnv(value: string | undefined, defaultValue: boolean) {
  if (value == null) return defaultValue;
  const normalized = value.trim().toLowerCase();
  if (normalized === "true" || normalized === "1" || normalized === "yes") return true;
  if (normalized === "false" || normalized === "0" || normalized === "no") return false;
  return defaultValue;
}

export function getAiProvider(env: NodeJS.ProcessEnv = process.env): ProviderName {
  const geminiKey = String(env.GEMINI_API_KEY ?? "").trim();
  return geminiKey ? "gemini" : "fallback";
}

function getAiConfig(env: NodeJS.ProcessEnv = process.env) {
  const apiKey = String(env.GEMINI_API_KEY ?? "").trim();
  const model = String(env.GEMINI_MODEL ?? DEFAULT_GEMINI_MODEL).trim() || DEFAULT_GEMINI_MODEL;
  const baseUrl = String(env.GEMINI_BASE_URL ?? DEFAULT_GEMINI_BASE_URL).trim().replace(/\/+$/, "") || DEFAULT_GEMINI_BASE_URL;
  const enabled = apiKey ? truthyEnv(env.GEMINI_ENABLED, true) : false;
  return { apiKey, model, baseUrl, enabled };
}

export function getAiHealth(env: NodeJS.ProcessEnv = process.env) {
  const provider = getAiProvider(env);
  const { model, enabled } = getAiConfig(env);
  return {
    aiProvider: provider === "gemini" ? "Gemini" : "Fallback",
    aiModel: provider === "gemini" ? model : "fallback",
    aiEnabled: enabled
  };
}

async function geminiGenerateText(args: { env: NodeJS.ProcessEnv; prompt: string }): Promise<string> {
  const { apiKey, model, baseUrl } = getAiConfig(args.env);
  const url = `${baseUrl}/v1beta/models/${encodeURIComponent(model)}:generateContent?key=${encodeURIComponent(apiKey)}`;

  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      contents: [{ role: "user", parts: [{ text: args.prompt }] }],
      generationConfig: { temperature: 0.2 }
    })
  });

  if (!response.ok) {
    const details = await response.text().catch(() => "");
    throw new Error(`Gemini request failed (${response.status}). ${details}`.trim());
  }

  const data = (await response.json()) as {
    candidates?: Array<{ content?: { parts?: Array<{ text?: string }> } }>;
  };
  const text = data.candidates?.[0]?.content?.parts?.[0]?.text ?? "";
  return String(text);
}

interface ScheduleRequest {
  selectedDesiredCourses?: string[];
  completedCourses?: string[];
  priorities?: PriorityMode;
  remainingRequirements?: string[];
  existingSchedule?: Array<{ courseCode: string; days?: string; time?: string }>;
  constraints?: { maxCourses?: number; timeWindow?: string };
}

interface NormalizedContext {
  completedCourses: string[];
  eligible: Array<Record<string, unknown>>;
  eligibleCodeSet: Set<string>;
  completedSet: Set<string>;
}

function normalizeContext(req: ScheduleRequest): NormalizedContext {
  const completedCourses = (req.completedCourses ?? []).map((c) => String(c).trim()).filter(Boolean);
  const completedSet = new Set(completedCourses.map((c) => c.toUpperCase()));
  const eligible = (req.selectedDesiredCourses ?? []).length
    ? (req.selectedDesiredCourses ?? []).map((code) => ({ code: String(code) }))
    : [];
  const eligibleCodeSet = new Set(eligible.map((c) => String(c.code ?? "").toUpperCase()).filter(Boolean));
  return { completedCourses, eligible, eligibleCodeSet, completedSet };
}

function buildPrompt(args: { context: NormalizedContext; req: ScheduleRequest }) {
  const priorities = args.req.priorities ?? "balanced";
  const desired = (args.req.selectedDesiredCourses ?? []).join(", ");
  const completed = args.context.completedCourses.join(", ");
  return [
    "You are a schedule planning assistant.",
    `Priorities: ${priorities}`,
    `Desired courses: ${desired || "(none)"}`,
    `Completed courses: ${completed || "(none)"}`,
    "Return JSON only with shape { plans: [ { id, title, rationale, items: [ { courseCode, courseName } ] } ] }."
  ].join("\n");
}

type PlanItem = { courseCode: string; courseName: string };
export type AiPlan = { id: string; title: string; rationale: string; items: PlanItem[]; source: ProviderName };

function fallbackPlans(): AiPlan[] {
  return [
    {
      id: "fallback-1",
      title: "Fallback plan",
      rationale: "AI is not configured, so this is a heuristic fallback.",
      items: [],
      source: "fallback"
    }
  ];
}

function parseGeminiPlans(text: string): Omit<AiPlan, "source">[] | null {
  try {
    const parsed = JSON.parse(text) as { plans?: Array<Record<string, unknown>> };
    const plans = Array.isArray(parsed.plans) ? parsed.plans : null;
    if (!plans) return null;
    return plans.map((p, idx) => ({
      id: String(p.id ?? `plan-${idx + 1}`),
      title: String(p.title ?? ""),
      rationale: String(p.rationale ?? ""),
      items: Array.isArray(p.items)
        ? p.items.map((it) => ({
            courseCode: String((it as any).courseCode ?? ""),
            courseName: String((it as any).courseName ?? "")
          }))
        : []
    }));
  } catch {
    return null;
  }
}

export async function generateSchedulePlans(
  mode: "recommend" | "explain",
  req: ScheduleRequest,
  runtime?: { env?: NodeJS.ProcessEnv }
): Promise<AiPlan[]> {
  void mode;
  const env = runtime?.env ?? process.env;

  // Normalize + fetch eligible courses for context (kept to match original behavior surface).
  const normalized = normalizeContext(req);
  const eligibleResults = await getEligibleCourseResults();
  normalized.eligible = (eligibleResults ?? []) as Array<Record<string, unknown>>;

  const provider = getAiProvider(env);
  const { enabled } = getAiConfig(env);
  if (provider !== "gemini" || !enabled) return fallbackPlans();

  const prompt = buildPrompt({ context: normalized, req });
  const text = await geminiGenerateText({ env, prompt });

  const parsed = parseGeminiPlans(text);
  if (!parsed || parsed.length === 0) return fallbackPlans();

  return parsed.map((p) => ({ ...p, source: "gemini" as const }));
}

