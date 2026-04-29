import { describe, expect, test, vi } from "vitest";
import { generateSchedulePlans, getAiProvider } from "../api/src/ai/scheduleAi.js";

vi.mock("../api/src/services/courseService.js", () => ({
  getEligibleCourseResults: vi.fn(async () => [{ code: "CSE 130", name: "Programming Languages" }])
}));

describe("Jason AI provider selection", () => {
  // As a student, I get Gemini-backed recommendations when Gemini is configured by the team.
  test("prefers Gemini provider when GEMINI_API_KEY exists", () => {
    // Arrange
    const env = {
      GEMINI_API_KEY: "AIzaFakeKeyForTests",
      OPENAI_API_KEY: "sk-test-openai"
    };

    // Action
    const provider = getAiProvider(env);

    // Assert
    expect(provider).toBe("gemini");
  });

  // As a student, my configured AI provider is honored by schedule generation at runtime.
  test("uses injected runtime env for provider selection", async () => {
    // Arrange
    const env = { GEMINI_API_KEY: "", OPENAI_API_KEY: "" } as NodeJS.ProcessEnv;

    // Action
    const plans = await generateSchedulePlans("recommend", { priorities: "balanced" }, { env });

    // Assert
    expect(plans[0].source).toBe("fallback");
    expect(Array.isArray(plans)).toBe(true);
  });
});
