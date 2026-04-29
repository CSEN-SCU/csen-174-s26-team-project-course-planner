import { describe, expect, test, vi } from "vitest";
import { generateSchedulePlans } from "../api/src/ai/scheduleAi.js";

vi.mock("../api/src/services/courseService.js", () => ({
  getEligibleCourseResults: vi.fn(async () => [{ code: "CSE 130", name: "Programming Languages" }])
}));

describe("Jason future sprint behavior", () => {
  // As a student, I want class swap alternatives so I can replace one course without regenerating everything.
  test("includes alternative course options for each recommended plan item", async () => {
    // Arrange
    vi.stubEnv("GEMINI_API_KEY", "");
    vi.stubEnv("OPENAI_API_KEY", "");

    // Action
    const plans = await generateSchedulePlans("recommend", { priorities: "balanced" });

    // Assert
    expect(Array.isArray(plans[0]?.items)).toBe(true);
    expect(plans[0]?.items.length).toBeGreaterThan(0);
    expect(plans[0]?.items[0]).toHaveProperty("alternatives");
  });
});
