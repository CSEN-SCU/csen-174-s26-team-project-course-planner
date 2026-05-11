import { describe, expect, test, vi } from "vitest";
import { generateSchedulePlans } from "../../bridges/api/ai/scheduleAi";

vi.mock("../../bridges/api/services/courseService.js", () => ({
  getEligibleCourseResults: vi.fn(async () => [{ code: "CSE 130", name: "Programming Languages" }])
}));

describe("Jason course alternatives", () => {
  test.skip("includes course alternatives for each recommended item (reason=deferred to later sprint: alternatives not implemented in plan items yet)", async () => {
    // Arrange
    const env = { GEMINI_API_KEY: "" } as NodeJS.ProcessEnv;

    // Action
    const plans = await generateSchedulePlans("recommend", { priorities: "balanced" }, { env });

    // Assert
    expect(plans[0]?.items?.[0]).toHaveProperty("alternatives");
  });
});

