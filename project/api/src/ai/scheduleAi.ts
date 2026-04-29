import type { PriorityMode } from "../utils/priority.js";
import { getEligibleCourseResults } from "../services/courseService.js";

type ProviderName = "gemini" | "fallback";

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

const fourYearPlanTerms: string[][] = [
  ["COEN 19", "CTW 1", "MATH 11", "CHEM 11", "COEN 10", "ENGR 1"],
  ["CTW 2", "MATH 12", "PHYS 31", "COEN 11"],
  ["MATH 13", "PHYS 32", "COEN 12"],
  ["CI 1", "MATH 14", "PHYS 33", "COEN 21"],
  ["CI 2", "AMTH 106", "AMTH 108", "COEN 79"],
  ["RTC 1", "MATH 53", "ELEN 50", "COEN 20"],
  ["ELEN 153", "COEN 177", "COEN 146", "COEN 161"],
  ["COEN 171", "COEN 179", "COEN 168"],
  ["ENGL 181", "COEN 181"],
  ["COEN 174", "COEN 194", "EE 1", "UNIV 201"],
  ["COEN 175", "COEN 195", "EE 2", "UNIV 202"],
  ["COEN 122", "COEN 196", "EE 3"]
];

function getRecommendedNextTermCodes(completedSet: Set<string>, existingScheduleSet: Set<string>) {
  for (const term of fourYearPlanTerms) {
    const pending = term.filter((code) => !completedSet.has(code.toUpperCase()) && !existingScheduleSet.has(code.toUpperCase()));
    if (pending.length > 0) {
      return pending;
    }
  }
  return [];
}

async function buildScheduleContext(request: ScheduleRequest): Promise<NormalizedContext> {
  const completedCourses = request.completedCourses ?? [
    "COEN 19",
    "CTW 1",
    "CTW 2",
    "MATH 11",
    "MATH 12",
    "MATH 13",
    "CHEM 11",
    "PHYS 31",
    "PHYS 32",
    "COEN 10",
    "COEN 11",
    "COEN 12",
    "ENGR 1"
  ];
  const completedSet = new Set(completedCourses.map((code) => code.toUpperCase()));
  const eligible = await getEligibleCourseResults({
    completedCourses,
    filters: { timeWindow: request.constraints?.timeWindow ?? "" },
    mode: request.priorities ?? "balanced"
  });
  const eligibleCodeSet = new Set(eligible.map((course) => course.code.toUpperCase()));
  return { completedCourses, eligible, eligibleCodeSet, completedSet };
}

function samplePlans(kind: "recommend" | "complete", eligible: Array<Record<string, unknown>>) {
  const items = eligible.slice(0, 4).map((course) => {
    const sections = Array.isArray(course.sections) ? (course.sections as Array<Record<string, unknown>>) : [];
    const firstSection = sections[0] ?? {};
    return {
      courseCode: String(course.code ?? "TBD"),
      courseName: String(course.name ?? "Suggested Course"),
      days: String(firstSection.days ?? "MW"),
      time: String(firstSection.time ?? "10:00-11:00"),
      instructor: String(firstSection.instructor ?? "TBD"),
      quality: Number(firstSection.quality ?? course.quality ?? 0),
      difficulty: Number(firstSection.difficulty ?? course.avgDifficulty ?? 0)
    };
  });

  return [
    {
      id: `${kind}-sample`,
      title: kind === "recommend" ? "Sample Balanced Plan" : "Sample Completion Plan",
      rationale: "Demo suggestion generated from the current eligible course set.",
      source: "fallback",
      items
    }
  ];
}

function enforcePlanSize(
  rawItems: Array<Record<string, unknown>>,
  eligible: Array<Record<string, unknown>>,
  eligibleCodeSet: Set<string>,
  completedSet: Set<string>,
  existingScheduleSet: Set<string>,
  existingScheduleSlots: Array<{ days: string; time: string }>,
  targetCount: number,
  prioritizedCodes: string[],
  mode: PriorityMode
) {
  const parseRange = (time: string) => {
    const [start = "09:00", end = "10:00"] = time.split("-");
    const [sh = "9", sm = "0"] = start.split(":");
    const [eh = "10", em = "0"] = end.split(":");
    return {
      startMinutes: Number(sh) * 60 + Number(sm),
      endMinutes: Number(eh) * 60 + Number(em)
    };
  };

  const daysOverlap = (aDays: string, bDays: string) => aDays.split("").some((day) => bDays.includes(day));

  const timeOverlap = (aTime: string, bTime: string) => {
    const a = parseRange(aTime);
    const b = parseRange(bTime);
    return a.startMinutes < b.endMinutes && b.startMinutes < a.endMinutes;
  };

  const conflictsWith = (candidate: { days: string; time: string }, chosen: Array<{ days: string; time: string }>) =>
    chosen.some((item) => daysOverlap(candidate.days, item.days) && timeOverlap(candidate.time, item.time));

  const modeWeight = (quality: number, difficulty: number) => {
    if (mode === "quality") return quality * 2 - difficulty * 0.3;
    if (mode === "easy") return quality * 0.6 - difficulty * 2;
    return quality * 1.4 - difficulty;
  };

  const prioritizedSet = new Set(prioritizedCodes.map((code) => code.toUpperCase()));
  const prioritizedEligible = eligible.filter((course) => prioritizedSet.has(String(course.code ?? "").toUpperCase()));
  const remainingEligible = eligible.filter((course) => !prioritizedSet.has(String(course.code ?? "").toUpperCase()));
  const fillPool = [...prioritizedEligible, ...remainingEligible];

  const eligibleByCode = new Map(eligible.map((course) => [String(course.code ?? "").toUpperCase(), course]));

  const usedCodes = new Set<string>();
  const rankedRawItems: Array<Record<string, unknown>> = rawItems
    .map((item): Record<string, unknown> => {
      const code = String(item.courseCode ?? "").toUpperCase();
      const course = eligibleByCode.get(code);
      const quality = Number(item.quality ?? course?.quality ?? 0);
      const difficulty = Number(item.difficulty ?? course?.avgDifficulty ?? 0);
      return { ...item, quality, difficulty, __score: modeWeight(quality, difficulty) };
    })
    .sort((a, b) => Number((b as Record<string, unknown>).__score ?? 0) - Number((a as Record<string, unknown>).__score ?? 0));

  const normalized: Array<Record<string, unknown>> = rankedRawItems
    .filter((item) => {
      const code = String(item.courseCode ?? "").toUpperCase();
      if (!code) return false;
      if (!eligibleCodeSet.has(code)) return false;
      if (completedSet.has(code)) return false;
      if (existingScheduleSet.has(code)) return false;
      if (usedCodes.has(code)) return false;
      usedCodes.add(code);
      return true;
    })
    .map((item) => ({
      ...item,
      quality: Number(item.quality ?? 0),
      difficulty: Number(item.difficulty ?? 0)
    }));

  const chosenSlots: Array<{ days: string; time: string }> = [...existingScheduleSlots];
  const normalizedNoConflicts: Array<Record<string, unknown>> = [];
  for (const item of normalized) {
    const days = String(item.days ?? "");
    const time = String(item.time ?? "");
    if (!days || !time) continue;
    if (!conflictsWith({ days, time }, chosenSlots)) {
      chosenSlots.push({ days, time });
      normalizedNoConflicts.push(item);
    }
  }

  for (const course of fillPool) {
    if (normalizedNoConflicts.length >= targetCount) break;
    const code = String(course.code ?? "").toUpperCase();
    if (!code || usedCodes.has(code) || completedSet.has(code) || existingScheduleSet.has(code)) continue;
    const sections = Array.isArray(course.sections) ? (course.sections as Array<Record<string, unknown>>) : [];
    const sortedSections = [...sections].sort(
      (a, b) =>
        modeWeight(Number(b.quality ?? 0), Number(b.difficulty ?? 0)) -
        modeWeight(Number(a.quality ?? 0), Number(a.difficulty ?? 0))
    );
    const section =
      sortedSections.find((candidate) => {
        const days = String(candidate.days ?? "");
        const time = String(candidate.time ?? "");
        if (!days || !time) return false;
        return !conflictsWith({ days, time }, chosenSlots);
      }) ?? sortedSections[0] ?? {};
    if (!section.days || !section.time) continue;

    normalizedNoConflicts.push({
      courseCode: String(course.code ?? "TBD"),
      courseName: String(course.name ?? "Suggested Course"),
      days: String(section.days ?? "MW"),
      time: String(section.time ?? "10:00-11:00"),
      instructor: String(section.instructor ?? "TBD"),
      quality: Number(section.quality ?? course.quality ?? 0),
      difficulty: Number(section.difficulty ?? course.avgDifficulty ?? 0)
    });
    chosenSlots.push({ days: String(section.days), time: String(section.time) });
    usedCodes.add(code);
  }

  const major = normalizedNoConflicts.filter((item) => String(item.courseCode ?? "").startsWith("COEN") || String(item.courseCode ?? "").startsWith("ELEN"));
  const core = normalizedNoConflicts.filter((item) => !major.includes(item));
  const balanced =
    targetCount >= 2 && major.length > 0 && core.length > 0
      ? [major[0], core[0], ...normalizedNoConflicts.filter((item) => item !== major[0] && item !== core[0])]
      : normalizedNoConflicts;

  return balanced.slice(0, targetCount);
}

export async function generateSchedulePlans(
  kind: "recommend" | "complete",
  request: ScheduleRequest,
  runtime?: { env?: NodeJS.ProcessEnv }
) {
  const { completedCourses, eligible, eligibleCodeSet, completedSet } = await buildScheduleContext(request);
  const existingScheduleSet = new Set((request.existingSchedule ?? []).map((course) => course.courseCode.toUpperCase()));
  const existingScheduleSlots = (request.existingSchedule ?? [])
    .filter((course) => course.days && course.time)
    .map((course) => ({ days: String(course.days), time: String(course.time) }));
  const recommendedNextTermCodes = getRecommendedNextTermCodes(completedSet, existingScheduleSet);
  const targetCount = recommendedNextTermCodes.length > 0 ? recommendedNextTermCodes.length : request.constraints?.maxCourses ?? 3;

  const env = runtime?.env ?? process.env;
  const { enabled } = getAiConfig(env);
  if (!enabled) {
    return samplePlans(kind, eligible).map((plan) => ({
      ...plan,
      items: enforcePlanSize(
        (Array.isArray(plan.items) ? plan.items : []) as Array<Record<string, unknown>>,
        eligible,
        eligibleCodeSet,
        completedSet,
        existingScheduleSet,
        existingScheduleSlots,
        targetCount,
        recommendedNextTermCodes,
        request.priorities ?? "balanced"
      ),
      coursePoolSize: eligible.length
    }));
  }

  const prompt = [
    "You are helping build a student schedule for an SCU course-planning prototype.",
    `Task: ${kind}.`,
    `Priorities: ${request.priorities ?? "balanced"}.`,
    `Completed courses (must NEVER be recommended): ${completedCourses.join(", ")}.`,
    `Remaining requirements: ${(request.remainingRequirements ?? []).join(", ") || "none provided"}.`,
    `Existing schedule: ${JSON.stringify(request.existingSchedule ?? [])}.`,
    `Desired courses: ${(request.selectedDesiredCourses ?? []).join(", ") || "none provided"}.`,
    "Return strict JSON with shape: {\\\"plans\\\":[{\\\"id\\\":string,\\\"title\\\":string,\\\"rationale\\\":string,\\\"source\\\":\\\"gemini\\\",\\\"items\\\":[{\\\"courseCode\\\":string,\\\"courseName\\\":string,\\\"days\\\":string,\\\"time\\\":string,\\\"instructor\\\":string,\\\"quality\\\":number,\\\"difficulty\\\":number}]}]}",
    `Eligible courses: ${JSON.stringify(eligible.slice(0, 10))}`
  ].join("\n");

  try {
    const raw = await geminiGenerateText({ env, prompt });
    const parsed = JSON.parse(raw) as { plans?: Array<Record<string, unknown>> };
    return (parsed.plans ?? []).map((plan, index) => {
      return {
        id: String(plan.id ?? `${kind}-${index}`),
        title: String(plan.title ?? "AI Plan"),
        rationale: String(plan.rationale ?? "AI-generated suggestion."),
        source: "gemini",
        items: enforcePlanSize(
          (Array.isArray(plan.items) ? plan.items : []) as Array<Record<string, unknown>>,
          eligible,
          eligibleCodeSet,
          completedSet,
          existingScheduleSet,
          existingScheduleSlots,
          targetCount,
          recommendedNextTermCodes,
          request.priorities ?? "balanced"
        )
      };
    });
  } catch (error) {
    const sample = samplePlans(kind, eligible).map((plan) => ({ ...plan, coursePoolSize: eligible.length }));
    return sample;
  }
}

export async function generateScheduleChatReply(request: ScheduleRequest, message: string) {
  const { completedCourses, eligible } = await buildScheduleContext(request);
  const existingSchedule = request.existingSchedule ?? [];
  const existingCodes = existingSchedule.map((course) => course.courseCode);

  const env = process.env;
  const { enabled } = getAiConfig(env);
  if (!enabled) {
    return {
      answer:
        "I can help with planning strategy. Tell me your target workload, preferred days/times, and whether you care more about easier classes or stronger professor quality.",
      source: "fallback"
    };
  }

  const prompt = [
    "You are an advising-style AI assistant for an SCU course-planning prototype.",
    "Give concise, practical answers in plain language for undergrads.",
    "Keep responses under 3 short sentences. Do not output long lists unless explicitly asked.",
    "If the user asks to generate/build a schedule, briefly acknowledge and ask one clarifying preference only if needed.",
    `Student message: ${message}`,
    `Priorities: ${request.priorities ?? "balanced"}.`,
    `Completed courses: ${completedCourses.join(", ") || "none provided"}.`,
    `Remaining requirements: ${(request.remainingRequirements ?? []).join(", ") || "none provided"}.`,
    `Existing scheduled courses: ${existingCodes.join(", ") || "none yet"}.`,
    `Current eligible options: ${JSON.stringify(eligible.slice(0, 10))}`
  ].join("\n");

  try {
    const answer = (await geminiGenerateText({ env, prompt })).trim() || "I could not generate advice right now.";
    return { answer, source: "gemini" };
  } catch {
    return {
      answer:
        "I can still help in sample mode. Try asking: 'Give me an easier 3-course quarter with minimal conflicts on Tue/Thu.'",
      source: "fallback"
    };
  }
}
