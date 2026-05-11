import { describe, expect, test, vi } from "vitest";
import { generateSchedulePlans } from "../../bridges/api/ai/scheduleAi";

vi.mock("../../bridges/api/services/courseService.js", () => ({
  getEligibleCourseResults: vi.fn(async () => [{ code: "CSE 130", name: "Programming Languages" }])
}));

describe("Jason plan warnings", () => {
  test.skip("includes non-empty warnings metadata for plan quality checks (reason=deferred to later sprint: warnings metadata not implemented yet)", async () => {
    // Arrange
    const env = { GEMINI_API_KEY: "" } as NodeJS.ProcessEnv;

    // Action
    const plans = await generateSchedulePlans("recommend", { priorities: "balanced" }, { env });

    // Assert
    expect(Array.isArray(plans[0]?.warnings)).toBe(true);
    expect(plans[0]?.warnings.length).toBeGreaterThan(0);
  });
});

