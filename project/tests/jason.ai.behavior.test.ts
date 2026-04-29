import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { generateSchedulePlans } from "../api/src/ai/scheduleAi.js";

vi.mock("../api/src/services/courseService.js", () => ({
  getEligibleCourseResults: vi.fn(async () => [{ code: "CSE 130", name: "Programming Languages" }])
}));

describe("Jason AI output behavior", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });
  afterEach(() => {
    vi.unstubAllEnvs();
    vi.unstubAllGlobals();
  });

  // Returns structured recommendation JSON so the UI can render plans reliably.
  test("returns AI plans with required fields when Gemini responds with JSON", async () => {
    // Arrange
    vi.stubEnv("GEMINI_API_KEY", "AIzaFakeKeyForTests");
    const fetchMock = vi.fn(async () => ({
      ok: true,
      json: async () => ({
        candidates: [
          {
            content: {
              parts: [
                {
                  text: JSON.stringify({
                    plans: [
                      {
                        id: "plan-1",
                        title: "Balanced plan",
                        rationale: "Balances workload and quality",
                        items: [{ courseCode: "CSE 130", courseName: "Programming Languages" }]
                      }
                    ]
                  })
                }
              ]
            }
          }
        ]
      })
    }));
    vi.stubGlobal("fetch", fetchMock);

    // Action
    const plans = await generateSchedulePlans(
      "recommend",
      { priorities: "balanced" },
      { env: { GEMINI_API_KEY: "AIzaFakeKeyForTests" } as NodeJS.ProcessEnv }
    );

    // Assert
    expect(plans.length).toBeGreaterThan(0);
    expect(typeof plans[0].id).toBe("string");
    expect(typeof plans[0].title).toBe("string");
    expect(typeof plans[0].rationale).toBe("string");
    expect(plans[0].source).toBe("gemini");
  });
});
