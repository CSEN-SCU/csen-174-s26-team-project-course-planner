import { describe, expect, test, vi } from "vitest";
import { generateSchedulePlans } from "../../bridges/api/ai/scheduleAi";

vi.mock("../../bridges/api/services/courseService.js", () => ({
  getEligibleCourseResults: vi.fn(async () => [{ code: "CSE 130", name: "Programming Languages" }])
}));

describe("Jason plan confidence score", () => {
  test.skip("includes a confidenceScore on each returned plan (reason=deferred to later sprint: confidence scoring not implemented yet)", async () => {
    // Arrange
    const env = { GEMINI_API_KEY: "" } as NodeJS.ProcessEnv;

    // Action
    const plans = await generateSchedulePlans("recommend", { priorities: "balanced" }, { env });

    // Assert
    expect(plans[0]).toHaveProperty("confidenceScore");
  });
});

