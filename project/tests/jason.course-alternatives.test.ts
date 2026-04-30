import { describe, expect, test, vi } from "vitest";
import { generateSchedulePlans } from "../api/src/ai/scheduleAi.js";

vi.mock("../api/src/services/courseService.js", () => ({
  getEligibleCourseResults: vi.fn(async () => [{ code: "CSE 130", name: "Programming Languages" }])
}));

describe("Jason course alternatives", () => {
  test("includes course alternatives for each recommended item", async () => {
    // Arrange
    const env = { GEMINI_API_KEY: "" } as NodeJS.ProcessEnv;

    // Action
    const plans = await generateSchedulePlans("recommend", { priorities: "balanced" }, { env });

    // Assert
    expect(plans[0]?.items?.[0]).toHaveProperty("alternatives");
  });
});
